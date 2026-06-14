from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    database_url: str
    aws_access_key_id: str
    aws_secret_access_key: str
    aws_region: str
    s3_bucket_name: str

    @classmethod
    def from_env(cls) -> "Settings":
        required_variables = {
            "OPENAI_API_KEY": "openai_api_key",
            "DATABASE_URL": "database_url",
            "AWS_ACCESS_KEY_ID": "aws_access_key_id",
            "AWS_SECRET_ACCESS_KEY": "aws_secret_access_key",
            "AWS_REGION": "aws_region",
            "S3_BUCKET_NAME": "s3_bucket_name",
        }
        missing_variables = [
            variable
            for variable in required_variables
            if not os.getenv(variable, "").strip()
        ]
        if missing_variables:
            raise RuntimeError(
                "Missing required environment variables: "
                + ", ".join(missing_variables)
            )

        return cls(
            **{
                field_name: os.environ[variable]
                for variable, field_name in required_variables.items()
            }
        )


settings = Settings.from_env()
