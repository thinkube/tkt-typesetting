# Copyright Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: MIT

# app/core/config.py
import os
from typing import List, Optional
from pydantic import validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # API settings
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = os.environ.get("APP_TITLE", "Web Application")

    # CORS settings
    BACKEND_CORS_ORIGINS: List[str] = []

    # Keycloak settings
    KEYCLOAK_URL: str
    KEYCLOAK_REALM: str
    KEYCLOAK_CLIENT_ID: str
    KEYCLOAK_CLIENT_SECRET: str
    KEYCLOAK_VERIFY_SSL: bool = True

    # Frontend URL for redirects
    FRONTEND_URL: str

    # PostgreSQL settings - all from environment
    POSTGRES_HOST: str = "postgresql-official.postgres.svc.cluster.local"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str = os.environ.get("APP_NAME", "webapp").replace('-', '_')

    # Allow DATABASE_URL to be overridden by environment
    DATABASE_URL: Optional[str] = None

    # The application's name: its namespace and its prefix in the artifact bucket.
    APP_NAME: str

    # Thinkube Storage, set by the platform on every container.
    SEAWEEDFS_ENDPOINT: str
    SEAWEEDFS_ACCESS_KEY: str
    SEAWEEDFS_SECRET_KEY: str

    # Argo Workflows, set by `services: [workflows]` in thinkube.yaml.
    WORKFLOWS_NAMESPACE: str
    WORKFLOWS_SERVER_URL: str
    WORKFLOWS_SERVICE_ACCOUNT: str
    WORKFLOWS_UI_URL: str
    CONTAINER_IMAGE_BACKEND: str

    # Largest manuscript accepted, in megabytes.
    MAX_UPLOAD_MB: int = 20

    @validator("DATABASE_URL", pre=True)
    def construct_database_url(cls, v, values):
        """Use DATABASE_URL from environment or construct from parts."""
        if v:
            return v
        # Construct from individual settings
        user = values.get("POSTGRES_USER")
        password = values.get("POSTGRES_PASSWORD")
        host = values.get("POSTGRES_HOST")
        port = values.get("POSTGRES_PORT")
        db = values.get("POSTGRES_DB")
        return f"postgresql://{user}:{password}@{host}:{port}/{db}"

    class Config:
        case_sensitive = True
        env_file = ".env"


settings = Settings()
