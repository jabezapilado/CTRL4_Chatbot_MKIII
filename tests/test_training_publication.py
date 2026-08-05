"""Regression coverage for version-specific emotion-model publication."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from ai_engine.core.training.evaluate_model import REQUIRED_EVALUATION_FILES
from ai_engine.core.training.train_emotion_model import (
    LANGUAGE,
    get_next_version,
    publish_evaluation_docs,
    publish_model,
)


def _write_publishable_evaluation(directory: Path, marker: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for filename in REQUIRED_EVALUATION_FILES:
        (directory / filename).write_text(marker, encoding="utf-8")


class TrainingPublicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self._temporary_directory.name)
        self.models_dir = self.root / "models"
        self.docs_models_dir = self.root / "docs" / "english_model"
        self.model_output_dir = self.root / "training-output"
        self.model_output_dir.mkdir(parents=True)
        (self.model_output_dir / "model.marker").write_text("v10", encoding="utf-8")
        (self.model_output_dir / "training_history.json").write_text(
            "[]",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self._temporary_directory.cleanup()

    def _seed_prior_versions(self) -> None:
        for version in range(1, 10):
            (self.models_dir / LANGUAGE / f"v{version}").mkdir(parents=True)
            docs_version = self.docs_models_dir / f"v{version}"
            docs_version.mkdir(parents=True)
            (docs_version / "historical.txt").write_text(
                f"v{version}-historical",
                encoding="utf-8",
            )

    def test_evaluation_finishes_before_v10_or_latest_are_published(self) -> None:
        self._seed_prior_versions()
        existing_v1_docs = self.docs_models_dir / "v1"
        observed = []

        def evaluate(*, model_dir, output_dir, history_path):
            observed.append((Path(model_dir), Path(output_dir), Path(history_path)))
            self.assertFalse((self.models_dir / LANGUAGE / "v10").exists())
            self.assertFalse((self.models_dir / LANGUAGE / "latest").exists())
            _write_publishable_evaluation(Path(output_dir), "v10-metrics")

        version_dir, latest_dir, docs_version_dir, docs_latest_dir = publish_model(
            model_output_dir=self.model_output_dir,
            models_dir=self.models_dir,
            docs_models_dir=self.docs_models_dir,
            evaluation_runner=evaluate,
            update_latest_alias=True,
        )

        self.assertEqual(version_dir.name, "v10")
        self.assertEqual(len(observed), 1)
        self.assertTrue(observed[0][0].name.startswith(".v10.staging-"))
        self.assertTrue((version_dir / "evaluation" / "overall_metrics.json").is_file())
        self.assertEqual((latest_dir / "model.marker").read_text(encoding="utf-8"), "v10")
        self.assertEqual(
            (docs_version_dir / "evaluation" / "overall_metrics.json").read_text(
                encoding="utf-8"
            ),
            "v10-metrics",
        )
        self.assertEqual(
            (docs_latest_dir / "evaluation" / "overall_metrics.json").read_text(
                encoding="utf-8"
            ),
            "v10-metrics",
        )
        self.assertEqual(
            (existing_v1_docs / "historical.txt").read_text(encoding="utf-8"),
            "v1-historical",
        )
        for version in range(1, 10):
            self.assertEqual(
                (
                    self.docs_models_dir / f"v{version}" / "historical.txt"
                ).read_text(encoding="utf-8"),
                f"v{version}-historical",
            )

    def test_failed_or_incomplete_evaluation_publishes_nothing(self) -> None:
        self._seed_prior_versions()
        preserved_docs = self.docs_models_dir / "v1"

        def fail_evaluation(**_kwargs):
            raise RuntimeError("evaluation failed")

        with self.assertRaisesRegex(RuntimeError, "evaluation failed"):
            publish_model(
                model_output_dir=self.model_output_dir,
                models_dir=self.models_dir,
                docs_models_dir=self.docs_models_dir,
                evaluation_runner=fail_evaluation,
            )

        self.assertFalse((self.models_dir / LANGUAGE / "v10").exists())
        self.assertFalse((self.docs_models_dir / "v10").exists())
        self.assertEqual(
            (preserved_docs / "historical.txt").read_text(encoding="utf-8"),
            "v1-historical",
        )

        def incomplete_evaluation(**_kwargs):
            return None

        with self.assertRaises(FileNotFoundError):
            publish_model(
                model_output_dir=self.model_output_dir,
                models_dir=self.models_dir,
                docs_models_dir=self.docs_models_dir,
                evaluation_runner=incomplete_evaluation,
            )

        self.assertFalse((self.models_dir / LANGUAGE / "v10").exists())
        self.assertFalse((self.docs_models_dir / "v10").exists())

    def test_version_docs_stay_isolated_while_latest_tracks_selected_version(self) -> None:
        first = self.root / "first-evaluation"
        second = self.root / "second-evaluation"
        _write_publishable_evaluation(first, "v10-metrics")
        _write_publishable_evaluation(second, "v11-metrics")

        publish_evaluation_docs(
            first,
            self.docs_models_dir / "v10",
            self.docs_models_dir / "latest",
        )
        publish_evaluation_docs(
            second,
            self.docs_models_dir / "v11",
            self.docs_models_dir / "latest",
        )

        self.assertEqual(
            (self.docs_models_dir / "v10" / "evaluation" / "overall_metrics.json").read_text(
                encoding="utf-8"
            ),
            "v10-metrics",
        )
        self.assertEqual(
            (self.docs_models_dir / "v11" / "evaluation" / "overall_metrics.json").read_text(
                encoding="utf-8"
            ),
            "v11-metrics",
        )
        self.assertEqual(
            (self.docs_models_dir / "latest" / "evaluation" / "overall_metrics.json").read_text(
                encoding="utf-8"
            ),
            "v11-metrics",
        )

    def test_external_runtime_alias_is_not_replaced_by_training_publication(self) -> None:
        self._seed_prior_versions()
        runtime_alias = self.models_dir / LANGUAGE / "latest"
        runtime_alias.mkdir(parents=True)
        (runtime_alias / "runtime_artifact_manifest.json").write_text(
            "externally-provisioned",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(RuntimeError, "externally provisioned"):
            publish_model(
                model_output_dir=self.model_output_dir,
                models_dir=self.models_dir,
                docs_models_dir=self.docs_models_dir,
                evaluation_runner=lambda **_kwargs: None,
                update_latest_alias=True,
            )

        self.assertEqual(
            (runtime_alias / "runtime_artifact_manifest.json").read_text(
                encoding="utf-8"
            ),
            "externally-provisioned",
        )
        self.assertFalse((self.models_dir / LANGUAGE / "v10").exists())

    def test_documentation_history_prevents_version_reuse_in_a_clean_checkout(self) -> None:
        for version in range(1, 8):
            (self.docs_models_dir / f"v{version}").mkdir(parents=True)

        next_version = get_next_version(self.models_dir, self.docs_models_dir)

        self.assertEqual(next_version.name, "v8")


if __name__ == "__main__":
    unittest.main()
