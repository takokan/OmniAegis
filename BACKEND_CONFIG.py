# Backend API Configuration Helper
# Update decision_layer/shared/config.py to use these environment variables

import os
from typing import Optional

class BackendConfig:
    """Backend configuration loaded from environment variables"""
    
    @staticmethod
    def get_backend_url() -> str:
        """Get backend API URL for frontend"""
        host = os.getenv("API_HOST", "0.0.0.0")
        port = os.getenv("API_PORT", "8000")
        # Replace 0.0.0.0 with localhost for browser
        if host == "0.0.0.0":
            host = "localhost"
        return f"http://{host}:{port}"
    
    @staticmethod
    def get_cors_origins() -> list[str]:
        """Get CORS allowed origins"""
        origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000")
        return [o.strip() for o in origins.split(",")]
    
    @staticmethod
    def get_blockchain_config() -> dict:
        """Get blockchain configuration"""
        return {
            "rpc_url": os.getenv("POLYGON_RPC_URL", "http://127.0.0.1:8545"),
            "private_key": os.getenv("POLYGON_PRIVATE_KEY"),
            "chain_id": int(os.getenv("POLYGON_CHAIN_ID", "31337")),
            "merkle_anchor": os.getenv("MERKLE_ANCHOR_CONTRACT", ""),
            "sentinel_audit": os.getenv("SENTINEL_AUDIT_CONTRACT", ""),
            "policy_registry": os.getenv("POLICY_REGISTRY_CONTRACT", ""),
        }
    
    @staticmethod
    def get_ipfs_config() -> dict:
        """Get IPFS configuration"""
        return {
            "api_url": os.getenv("IPFS_API_URL", "http://127.0.0.1:5001"),
            "pinata_key": os.getenv("PINATA_API_KEY"),
            "pinata_secret": os.getenv("PINATA_API_SECRET"),
        }
    
    @staticmethod
    def is_development() -> bool:
        """Check if running in development mode"""
        return os.getenv("ENVIRONMENT", "development") == "development"
