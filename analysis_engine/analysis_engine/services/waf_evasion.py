from __future__ import annotations

import random
from dataclasses import dataclass


DEFAULT_UAS = [
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]


@dataclass(frozen=True)
class RequestIdentity:
    user_agent: str
    proxy: str | None


class RotatingIdentityProvider:
    def __init__(self, user_agents: list[str] | None, proxies: list[str] | None) -> None:
        self.user_agents = user_agents or DEFAULT_UAS
        self.proxies = proxies or []

    def choose(self) -> RequestIdentity:
        ua = random.choice(self.user_agents)
        proxy = random.choice(self.proxies) if self.proxies else None
        return RequestIdentity(user_agent=ua, proxy=proxy)

