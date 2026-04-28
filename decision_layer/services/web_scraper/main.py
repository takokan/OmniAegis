from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from heapq import heappush
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.robotparser import RobotFileParser
import heapq

import httpx

try:
	from decision_layer.shared import get_redis_client
except ModuleNotFoundError:  # pragma: no cover
	from shared import get_redis_client


logger = logging.getLogger(__name__)


class CrawlSourceTier(str):
	tier_0 = "tier_0"
	tier_1 = "tier_1"
	tier_2 = "tier_2"
	tier_3 = "tier_3"


TIER_SCORES: dict[str, float] = {
	CrawlSourceTier.tier_0: 1.0,
	CrawlSourceTier.tier_1: 0.85,
	CrawlSourceTier.tier_2: 0.65,
	CrawlSourceTier.tier_3: 0.40,
}


@dataclass(frozen=True)
class CrawlSeed:
	url: str
	tier: str = CrawlSourceTier.tier_1
	priority: float = 0.75


@dataclass(frozen=True)
class CrawlPolicy:
	allowed_domains: tuple[str, ...] = ()
	blocked_domains: tuple[str, ...] = ()
	protected_terms: tuple[str, ...] = ()
	max_depth: int = 1
	max_pages: int = 100
	max_links_per_page: int = 25
	concurrency: int = 6
	request_timeout_seconds: float = 20.0
	respect_robots_txt: bool = True
	require_allowlist: bool = True
	min_emit_score: float = 0.55
	min_follow_score: float = 0.35
	user_agent: str = "OmniAegisCrawler/1.0 (+https://example.invalid)"


@dataclass(frozen=True)
class CrawlCandidate:
	url: str
	source_url: str
	canonical_url: str
	domain: str
	tier: str
	depth: int
	score: float
	title: str
	excerpt: str
	text: str
	keyword_hits: dict[str, int]
	content_type: str | None
	status_code: int
	content_digest: str
	links_found: int
	fetched_at: str
	metadata: dict[str, Any] = field(default_factory=dict)

	def to_dict(self) -> dict[str, Any]:
		return asdict(self)


class CandidateSink(Protocol):
	async def emit(self, candidate: CrawlCandidate) -> None:  # pragma: no cover - protocol
		...


class JSONLCandidateSink:
	def __init__(self, path: str | Path) -> None:
		self.path = Path(path)
		self.path.parent.mkdir(parents=True, exist_ok=True)
		self._lock = asyncio.Lock()

	async def emit(self, candidate: CrawlCandidate) -> None:
		line = json.dumps(candidate.to_dict(), ensure_ascii=False)
		async with self._lock:
			await asyncio.to_thread(self._append_line, line)

	def _append_line(self, line: str) -> None:
		with self.path.open("a", encoding="utf-8") as handle:
			handle.write(line)
			handle.write("\n")


class RedisCandidateSink:
	def __init__(self, stream_key: str = "sentinel:ingest:stream") -> None:
		self.stream_key = stream_key
		self._redis = None
		self._lock = asyncio.Lock()

	async def _client(self):
		if self._redis is None:
			self._redis = await get_redis_client()
		return self._redis

	async def emit(self, candidate: CrawlCandidate) -> None:
		client = await self._client()
		payload = candidate.to_dict()
		message = {
			"asset_id": payload["content_digest"],
			"source": payload["source_url"],
			"url": payload["url"],
			"canonical_url": payload["canonical_url"],
			"filename": payload["title"] or payload["content_digest"],
			"content_type": payload.get("content_type"),
			"modality": "web",
			"confidence_hint": f"{payload['score']:.4f}",
			"metadata": json.dumps(payload, ensure_ascii=False),
		}
		async with self._lock:
			await client.xadd(self.stream_key, message)


class _PageParser(HTMLParser):
	def __init__(self) -> None:
		super().__init__()
		self.title_parts: list[str] = []
		self.text_parts: list[str] = []
		self.links: list[str] = []
		self.meta: dict[str, str] = {}
		self._capture_title = False
		self._skip_depth = 0

	def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
		attr_map = {key.lower(): value for key, value in attrs if value is not None}
		if tag in {"script", "style", "noscript"}:
			self._skip_depth += 1
			return
		if tag == "title":
			self._capture_title = True
		if tag == "meta":
			name = attr_map.get("name") or attr_map.get("property")
			content = attr_map.get("content")
			if name and content:
				self.meta[name.lower()] = unescape(content.strip())
		if tag == "link" and (attr_map.get("rel") or "").lower() == "canonical":
			href = attr_map.get("href")
			if href:
				self.meta["canonical"] = unescape(href.strip())
		if tag == "a":
			href = attr_map.get("href")
			if href:
				self.links.append(unescape(href.strip()))

	def handle_endtag(self, tag: str) -> None:
		if tag in {"script", "style", "noscript"} and self._skip_depth > 0:
			self._skip_depth -= 1
		if tag == "title":
			self._capture_title = False

	def handle_data(self, data: str) -> None:
		if self._skip_depth > 0:
			return
		text = unescape(data).strip()
		if not text:
			return
		if self._capture_title:
			self.title_parts.append(text)
		self.text_parts.append(text)


class PrioritizedWebCrawler:
	def __init__(self, policy: CrawlPolicy, seeds: list[CrawlSeed], sink: CandidateSink) -> None:
		self.policy = policy
		self.seeds = seeds
		self.sink = sink
		self._robots_cache: dict[str, RobotFileParser | None] = {}
		self._seen_urls: set[str] = set()
		self._queued_urls: set[str] = set()
		seed_domains = {self._domain_from_url(seed.url) for seed in seeds if self._domain_from_url(seed.url)}
		self._allowed_domains = {domain.lower() for domain in (policy.allowed_domains or tuple(sorted(seed_domains)))}
		self._blocked_domains = {domain.lower() for domain in policy.blocked_domains}
		self._protected_terms = tuple(term.strip().lower() for term in policy.protected_terms if term.strip())

	@staticmethod
	def _domain_from_url(url: str) -> str:
		parsed = urlparse(url)
		return parsed.netloc.lower()

	@staticmethod
	def _normalize_url(url: str, base_url: str | None = None) -> str:
		absolute = urljoin(base_url, url) if base_url else url
		parsed = urlparse(absolute)
		path = parsed.path or "/"
		return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), path, parsed.params, parsed.query, ""))

	def _is_allowed_domain(self, url: str) -> bool:
		domain = self._domain_from_url(url)
		if not domain:
			return False
		if domain in self._blocked_domains:
			return False
		if not self.policy.require_allowlist:
			return True
		if not self._allowed_domains:
			return False
		return any(domain == allowed or domain.endswith(f".{allowed}") for allowed in self._allowed_domains)

	async def _robots_allowed(self, client: httpx.AsyncClient, url: str) -> bool:
		if not self.policy.respect_robots_txt:
			return True
		domain = self._domain_from_url(url)
		if domain in self._robots_cache:
			rp = self._robots_cache[domain]
			return rp.can_fetch(self.policy.user_agent, url) if rp is not None else True

		robots_url = urlunparse((urlparse(url).scheme, urlparse(url).netloc, "/robots.txt", "", "", ""))
		try:
			response = await client.get(robots_url, follow_redirects=True)
			if response.status_code >= 400:
				self._robots_cache[domain] = None
				return True
			parser = RobotFileParser()
			parser.set_url(robots_url)
			parser.parse(response.text.splitlines())
			self._robots_cache[domain] = parser
			return parser.can_fetch(self.policy.user_agent, url)
		except Exception:
			self._robots_cache[domain] = None
			return True

	def _count_term_hits(self, text: str) -> dict[str, int]:
		lower = text.lower()
		hits: dict[str, int] = {}
		for term in self._protected_terms:
			count = lower.count(term)
			if count > 0:
				hits[term] = count
		return hits

	def _tier_score(self, tier: str) -> float:
		return float(TIER_SCORES.get(tier, 0.5))

	def _score_text(self, text: str) -> float:
		hits = self._count_term_hits(text)
		if not hits:
			return 0.0
		return min(0.35, 0.08 * len(hits) + 0.03 * sum(min(count, 3) for count in hits.values()))

	def _score_url(self, url: str) -> float:
		parsed = urlparse(url)
		path = f"{parsed.netloc} {parsed.path} {parsed.query}".lower()
		return self._score_text(path)

	def _score_page(self, *, seed: CrawlSeed, url: str, title: str, text: str, content_type: str | None, status_code: int) -> float:
		score = self._tier_score(seed.tier)
		score += self._score_url(url)
		score += self._score_text(title)
		score += self._score_text(text[:8000])
		if content_type and "text/html" in content_type.lower():
			score += 0.03
		if status_code == 200:
			score += 0.02
		return max(0.0, min(1.0, score))

	def _score_link(self, *, seed: CrawlSeed, page_score: float, base_url: str, link_url: str) -> float:
		absolute = self._normalize_url(link_url, base_url)
		score = 0.45 * page_score
		score += 0.35 * self._tier_score(seed.tier)
		score += self._score_url(absolute)
		if self._domain_from_url(base_url) == self._domain_from_url(absolute):
			score += 0.10
		return max(0.0, min(1.0, score))

	@staticmethod
	def _extract_excerpt(text: str, max_words: int = 80) -> str:
		words = re.findall(r"\S+", text)
		return " ".join(words[:max_words])

	@staticmethod
	def _digest_text(text: str) -> str:
		return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()

	async def _fetch_page(self, client: httpx.AsyncClient, url: str) -> tuple[int, str | None, str, list[str], str, str, str]:
		response = await client.get(url, follow_redirects=True)
		content_type = response.headers.get("content-type")
		text = response.text if "text" in (content_type or "").lower() or "html" in (content_type or "").lower() else ""
		parser = _PageParser()
		if text:
			parser.feed(text)
		title = " ".join(parser.title_parts).strip() or parser.meta.get("title", "")
		page_text = " ".join(parser.text_parts).strip()
		canonical = parser.meta.get("canonical") or url
		return response.status_code, content_type, title, parser.links[: self.policy.max_links_per_page], page_text, canonical, response.url.__str__()

	async def run(self) -> list[CrawlCandidate]:
		results: list[CrawlCandidate] = []
		queue: list[tuple[float, int, CrawlSeed, str, int]] = []
		counter = 0

		for seed in self.seeds:
			normalized = self._normalize_url(seed.url)
			heappush(queue, (-float(seed.priority), counter, seed, normalized, 0))
			counter += 1

		limits = httpx.Limits(max_connections=self.policy.concurrency, max_keepalive_connections=self.policy.concurrency)
		timeout = httpx.Timeout(self.policy.request_timeout_seconds)
		headers = {"User-Agent": self.policy.user_agent}

		async with httpx.AsyncClient(timeout=timeout, limits=limits, headers=headers) as client:
			while queue and len(results) < self.policy.max_pages:
				_, _, seed, url, depth = heapq.heappop(queue)
				if url in self._seen_urls:
					continue
				self._seen_urls.add(url)

				if not self._is_allowed_domain(url):
					continue
				if not await self._robots_allowed(client, url):
					continue

				try:
					status_code, content_type, title, links, page_text, canonical, final_url = await self._fetch_page(client, url)
				except Exception as exc:
					logger.debug("Failed to fetch %s: %s", url, exc)
					continue

				page_score = self._score_page(
					seed=seed,
					url=final_url,
					title=title,
					text=page_text,
					content_type=content_type,
					status_code=status_code,
				)
				keyword_hits = self._count_term_hits(f"{title}\n{page_text}\n{final_url}")
				candidate = CrawlCandidate(
					url=final_url,
					source_url=url,
					canonical_url=canonical,
					domain=self._domain_from_url(final_url),
					tier=seed.tier,
					depth=depth,
					score=page_score,
					title=title,
					excerpt=self._extract_excerpt(page_text),
					text=page_text,
					keyword_hits=keyword_hits,
					content_type=content_type,
					status_code=status_code,
					content_digest=self._digest_text(f"{canonical}|{title}|{page_text[:12000]}"),
					links_found=len(links),
					fetched_at=datetime.now(timezone.utc).isoformat(),
					metadata={
						"source_priority": seed.priority,
						"final_url": final_url,
					},
				)

				if candidate.score >= self.policy.min_emit_score:
					results.append(candidate)
					await self.sink.emit(candidate)

				if depth >= self.policy.max_depth:
					continue

				for link in links[: self.policy.max_links_per_page]:
					next_url = self._normalize_url(link, base_url=final_url)
					if next_url in self._seen_urls or next_url in self._queued_urls:
						continue
					if not self._is_allowed_domain(next_url):
						continue
					link_score = self._score_link(seed=seed, page_score=page_score, base_url=final_url, link_url=next_url)
					if link_score < self.policy.min_follow_score:
						continue
					heappush(queue, (-link_score, counter, seed, next_url, depth + 1))
					self._queued_urls.add(next_url)
					counter += 1

		return results


def _parse_csv_values(values: list[str] | None) -> tuple[str, ...]:
	if not values:
		return ()
		
	return tuple(v.strip() for v in values if v and v.strip())


def _parse_seeds(urls: list[str], tier: str, priority: float) -> list[CrawlSeed]:
	seeds: list[CrawlSeed] = []
	for raw in urls:
		value = raw.strip()
		if not value:
			continue
		if value.startswith("{"):
			payload = json.loads(value)
			seeds.append(
				CrawlSeed(
					url=str(payload["url"]),
					tier=str(payload.get("tier", tier)),
					priority=float(payload.get("priority", priority)),
				)
			)
			continue
		seeds.append(CrawlSeed(url=value, tier=tier, priority=priority))
	return seeds


def _load_seed_file(path: str | None, default_tier: str, default_priority: float) -> list[CrawlSeed]:
	if not path:
		return []
	seed_path = Path(path)
	if not seed_path.exists():
		raise FileNotFoundError(seed_path)
	seeds: list[CrawlSeed] = []
	for line in seed_path.read_text(encoding="utf-8").splitlines():
		clean = line.strip()
		if not clean or clean.startswith("#"):
			continue
		if clean.startswith("{"):
			payload = json.loads(clean)
			seeds.append(
				CrawlSeed(
					url=str(payload["url"]),
					tier=str(payload.get("tier", default_tier)),
					priority=float(payload.get("priority", default_priority)),
				)
			)
			continue
		seeds.append(CrawlSeed(url=clean, tier=default_tier, priority=default_priority))
	return seeds


async def run_web_scraper(
	*,
	seed_urls: list[str],
	seed_file: str | None = None,
	allow_domains: list[str] | None = None,
	blocked_domains: list[str] | None = None,
	protected_terms: list[str] | None = None,
	max_depth: int = 1,
	max_pages: int = 100,
	max_links_per_page: int = 25,
	concurrency: int = 6,
	request_timeout_seconds: float = 20.0,
	respect_robots_txt: bool = True,
	require_allowlist: bool = True,
	min_emit_score: float = 0.55,
	min_follow_score: float = 0.35,
	user_agent: str = "OmniAegisCrawler/1.0 (+https://example.invalid)",
	output_jsonl: str | None = None,
	redis_stream: str | None = None,
	tier: str = CrawlSourceTier.tier_1,
	priority: float = 0.75,
	) -> list[CrawlCandidate]:
	seeds = _parse_seeds(seed_urls, tier=tier, priority=priority)
	seeds.extend(_load_seed_file(seed_file, default_tier=tier, default_priority=priority))
	if not seeds:
		raise ValueError("At least one seed URL or seed file entry is required")

	policy = CrawlPolicy(
		allowed_domains=tuple(sorted(set(_parse_csv_values(allow_domains)))),
		blocked_domains=tuple(sorted(set(_parse_csv_values(blocked_domains)))),
		protected_terms=tuple(sorted(set(_parse_csv_values(protected_terms)))),
		max_depth=max_depth,
		max_pages=max_pages,
		max_links_per_page=max_links_per_page,
		concurrency=concurrency,
		request_timeout_seconds=request_timeout_seconds,
		respect_robots_txt=respect_robots_txt,
		require_allowlist=require_allowlist,
		min_emit_score=min_emit_score,
		min_follow_score=min_follow_score,
		user_agent=user_agent,
	)

	if redis_stream:
		sink: CandidateSink = RedisCandidateSink(redis_stream)
	elif output_jsonl:
		sink = JSONLCandidateSink(output_jsonl)
	else:
		sink = JSONLCandidateSink("./artifacts/web_scraper_candidates.jsonl")

	crawler = PrioritizedWebCrawler(policy=policy, seeds=seeds, sink=sink)
	return await crawler.run()


def build_arg_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(description="Run the OmniAegis bounded web scraper")
	parser.add_argument("--seed", action="append", default=[], help="Seed URL or JSON blob with url/tier/priority")
	parser.add_argument("--seed-file", default=None, help="Path to newline-delimited seed URLs or JSON blobs")
	parser.add_argument("--allow-domain", action="append", default=[], help="Allowed domain, repeatable")
	parser.add_argument("--blocked-domain", action="append", default=[], help="Blocked domain, repeatable")
	parser.add_argument("--protected-term", action="append", default=[], help="Protected term, repeatable")
	parser.add_argument("--max-depth", type=int, default=1)
	parser.add_argument("--max-pages", type=int, default=100)
	parser.add_argument("--max-links-per-page", type=int, default=25)
	parser.add_argument("--concurrency", type=int, default=6)
	parser.add_argument("--request-timeout-seconds", type=float, default=20.0)
	parser.add_argument("--no-robots", action="store_true", help="Disable robots.txt checks")
	parser.add_argument("--no-allowlist", action="store_true", help="Disable allowlist restriction")
	parser.add_argument("--min-emit-score", type=float, default=0.55)
	parser.add_argument("--min-follow-score", type=float, default=0.35)
	parser.add_argument("--user-agent", default="OmniAegisCrawler/1.0 (+https://example.invalid)")
	parser.add_argument("--output-jsonl", default=None, help="Write candidates to a JSONL file")
	parser.add_argument("--redis-stream", default=None, help="Push candidates to a Redis stream")
	parser.add_argument("--tier", default=CrawlSourceTier.tier_1, help="Default tier for plain seed URLs")
	parser.add_argument("--priority", type=float, default=0.75, help="Default priority for plain seed URLs")
	return parser


def main(argv: list[str] | None = None) -> int:
	parser = build_arg_parser()
	args = parser.parse_args(argv)

	logging.basicConfig(
		level=os.getenv("LOG_LEVEL", "INFO"),
		format="%(asctime)s %(levelname)s %(name)s: %(message)s",
	)

	results = asyncio.run(
		run_web_scraper(
			seed_urls=args.seed,
			seed_file=args.seed_file,
			allow_domains=args.allow_domain,
			blocked_domains=args.blocked_domain,
			protected_terms=args.protected_term,
			max_depth=args.max_depth,
			max_pages=args.max_pages,
			max_links_per_page=args.max_links_per_page,
			concurrency=args.concurrency,
			request_timeout_seconds=args.request_timeout_seconds,
			respect_robots_txt=not args.no_robots,
			require_allowlist=not args.no_allowlist,
			min_emit_score=args.min_emit_score,
			min_follow_score=args.min_follow_score,
			user_agent=args.user_agent,
			output_jsonl=args.output_jsonl,
			redis_stream=args.redis_stream,
			tier=args.tier,
			priority=args.priority,
		)
	)

	print(json.dumps({"candidates": len(results), "output": args.output_jsonl or args.redis_stream or "./artifacts/web_scraper_candidates.jsonl"}, indent=2))
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
