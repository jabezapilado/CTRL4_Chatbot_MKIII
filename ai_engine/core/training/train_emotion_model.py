"""
Emotion Model Training

Fine-tunes the emotion classification model.

Author: CTRL4 Chatbot MK2
"""

import shutil
from pathlib import Path
from uuid import uuid4

from ai_engine.core.training.evaluate_model import main as evaluate_model
from ai_engine.core.training.evaluate_model import validate_evaluation_output
from ai_engine.core.training.dataset import prepare_dataset
from ai_engine.core.models.emotion_classifier import load_model
from ai_engine.core.tokenizers.tokenizer import load_tokenizer
from ai_engine.core.training.trainer import create_trainer
from ai_engine.core.utilities.config import load_config
import json


config = load_config("model_config.json")


MODELS_DIR = Path("ai_engine/models")
DOCS_MODELS_DIR = Path("docs/models/english_model")
LANGUAGE = "english"


def get_next_version(
    models_dir: Path = MODELS_DIR,
    docs_models_dir: Path = DOCS_MODELS_DIR,
):
    """Choose a new version without colliding with model or documentation history."""
    language_dir = Path(models_dir) / LANGUAGE
    language_dir.mkdir(parents=True, exist_ok=True)
    documentation_dir = Path(docs_models_dir)

    versions = []
    for directory in (language_dir, documentation_dir):
        if not directory.is_dir():
            continue
        for folder in directory.iterdir():
            if folder.is_dir() and folder.name.startswith("v"):
                try:
                    versions.append(int(folder.name[1:]))
                except ValueError:
                    pass

    next_version = max(versions, default=0) + 1

    return language_dir / f"v{next_version}"


def _stage_directory(source: Path, destination: Path) -> Path:
    """Copy a directory beside its destination before an atomic publish."""
    source = Path(source)
    destination = Path(destination)
    if not source.is_dir():
        raise FileNotFoundError(f"Source directory does not exist: {source}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.parent / f".{destination.name}.staging-{uuid4().hex}"
    shutil.copytree(source, staging)
    return staging


def _publish_staged_directory(
    staging: Path,
    destination: Path,
    *,
    replace_existing: bool,
) -> None:
    """Atomically publish a staged directory without destroying history first."""
    staging = Path(staging)
    destination = Path(destination)
    if destination.exists() and not replace_existing:
        raise FileExistsError(
            f"Refusing to overwrite existing version directory: {destination}"
        )

    backup = None
    if destination.exists():
        backup = destination.parent / f".{destination.name}.backup-{uuid4().hex}"
        destination.replace(backup)

    try:
        staging.replace(destination)
    except Exception:
        if backup is not None and backup.exists():
            backup.replace(destination)
        raise
    else:
        if backup is not None and backup.exists():
            shutil.rmtree(backup)


def _atomic_copy_directory(
    source: Path,
    destination: Path,
    *,
    replace_existing: bool,
) -> None:
    staging = _stage_directory(source, destination)
    try:
        _publish_staged_directory(
            staging,
            destination,
            replace_existing=replace_existing,
        )
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise


def publish_evaluation_docs(
    evaluation_dir: Path,
    docs_version_dir: Path,
    docs_latest_dir: Path,
    *,
    update_latest_alias: bool = True,
) -> tuple[Path, Path]:
    """Publish validated evaluation artifacts for one version and its latest alias."""
    evaluation_dir = validate_evaluation_output(evaluation_dir)
    docs_version_dir = Path(docs_version_dir)
    docs_latest_dir = Path(docs_latest_dir)

    if docs_version_dir.exists():
        raise FileExistsError(
            f"Refusing to overwrite existing documentation for {docs_version_dir.name}"
        )

    _atomic_copy_directory(
        evaluation_dir,
        docs_version_dir / "evaluation",
        replace_existing=False,
    )
    if update_latest_alias:
        _atomic_copy_directory(
            evaluation_dir,
            docs_latest_dir / "evaluation",
            replace_existing=True,
        )
    return docs_version_dir, docs_latest_dir


def publish_model(
    *,
    model_output_dir: Path | None = None,
    models_dir: Path = MODELS_DIR,
    docs_models_dir: Path = DOCS_MODELS_DIR,
    evaluation_runner=evaluate_model,
    update_latest_alias: bool = False,
) -> tuple[Path, Path, Path, Path]:
    """Evaluate one staged model before publishing a version and optional alias."""
    output_dir = Path(model_output_dir or config["output_dir"])
    models_dir = Path(models_dir)
    docs_models_dir = Path(docs_models_dir)
    version_dir = get_next_version(models_dir, docs_models_dir)
    latest_dir = models_dir / LANGUAGE / "latest"
    docs_version_dir = docs_models_dir / version_dir.name
    docs_latest_dir = docs_models_dir / "latest"

    if update_latest_alias and (latest_dir / "runtime_artifact_manifest.json").is_file():
        raise RuntimeError(
            "Refusing to replace the externally provisioned runtime alias. "
            "Provision and verify a new runtime artifact before promotion."
        )

    print(f"\nStaging model for evaluation as {version_dir.name}")
    staged_version_dir = _stage_directory(output_dir, version_dir)
    stale_evaluation_dir = staged_version_dir / "evaluation"
    if stale_evaluation_dir.exists():
        shutil.rmtree(stale_evaluation_dir)

    evaluation_dir = staged_version_dir / "evaluation"
    try:
        evaluation_runner(
            model_dir=staged_version_dir,
            output_dir=evaluation_dir,
            history_path=staged_version_dir / "training_history.json",
        )
        validate_evaluation_output(evaluation_dir)

        print(f"Publishing validated model to {version_dir}")
        _publish_staged_directory(
            staged_version_dir,
            version_dir,
            replace_existing=False,
        )

        if update_latest_alias:
            print("Updating latest model alias...")
            _atomic_copy_directory(
                version_dir,
                latest_dir,
                replace_existing=True,
            )

        print(f"Publishing evaluation docs to {docs_version_dir}")
        publish_evaluation_docs(
            version_dir / "evaluation",
            docs_version_dir,
            docs_latest_dir,
            update_latest_alias=update_latest_alias,
        )
    except Exception:
        if staged_version_dir.exists():
            shutil.rmtree(staged_version_dir)
        raise

    return version_dir, latest_dir, docs_version_dir, docs_latest_dir

def main():

    print()
    print("=" * 60)
    print("CTRL4 EMOTION MODEL TRAINING")
    print("=" * 60)

    print("\nPreparing dataset...")
    dataset = prepare_dataset()

    print("\nLoading tokenizer...")
    tokenizer = load_tokenizer()

    print("\nLoading model...")
    model = load_model()

    print("\nCreating trainer...")
    trainer = create_trainer(

        model=model,

        tokenizer=tokenizer,

        train_dataset=dataset["train"],

        validation_dataset=dataset["validation"]

    )

    print("\nStarting training...\n")

    trainer.train()

    print("\nEvaluating model...\n")

    metrics = trainer.evaluate()

    history_path = Path(config["output_dir"]) / "training_history.json"
    history_path.parent.mkdir(parents=True, exist_ok=True)

    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(trainer.state.log_history, f, indent=4)

    print(f"Version-specific training history saved to {history_path}")

    print("=" * 60)
    print("FINAL METRICS")
    print("=" * 60)

    for key, value in metrics.items():
        print(f"{key:<25}{value}")

    print()

    trainer.save_model(
        config["output_dir"]
    )

    tokenizer.save_pretrained(
        config["output_dir"]
    )

    print("=" * 60)
    print("MODEL SAVED")
    print("=" * 60)
    print(config["output_dir"])

    print("\nRunning version-specific evaluation and publication...\n")

    version_dir, latest_dir, docs_version_dir, docs_latest_dir = publish_model(
        model_output_dir=Path(config["output_dir"]),
    )

    print("\n" + "=" * 60)
    print("TRAINING COMPLETE")
    print("=" * 60)
    print(f"Published Model : {version_dir}")
    print(f"Latest Model    : unchanged at {latest_dir} (external promotion required)")
    print(f"Docs Model      : {docs_version_dir}")
    print(f"Docs Latest     : unchanged at {docs_latest_dir}")
    print(f"Evaluation      : {version_dir / 'evaluation'}")


if __name__ == "__main__":
    main()
