from pathlib import Path


def test_backend_package_imports() -> None:
    import novel_translation_backend

    assert novel_translation_backend.__name__ == "novel_translation_backend"


def test_required_root_scaffold_files_exist() -> None:
    root = Path(__file__).resolve().parents[2]

    for relative_path in [
        "backend",
        "frontend",
        "infra",
        "docker-compose.yml",
        ".env.example",
        ".gitignore",
        "README.md",
    ]:
        assert (root / relative_path).exists()


def test_env_example_contains_required_placeholders() -> None:
    root = Path(__file__).resolve().parents[2]
    env_example = (root / ".env.example").read_text()

    for key in [
        "ANTHROPIC_API_KEY",
        "DATABASE_URL",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_REGION",
        "S3_BUCKET_NAME",
    ]:
        assert f"{key}=" in env_example
