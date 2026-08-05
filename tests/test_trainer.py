import torch
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import ai_engine.core.training.trainer as trainer_module
from ai_engine.core.training.trainer import (
    compute_class_weights,
    configured_class_weight_power,
)


class TrainerTests(unittest.TestCase):
    def test_compute_class_weights_increases_rarity_penalty_when_requested(self):
        train_dataset = {"labels": [0, 0, 0, 0, 1, 1, 1, 2]}

        weights = compute_class_weights(train_dataset, 3, class_weight_power=0.75)

        self.assertIsInstance(weights, torch.Tensor)
        self.assertEqual(tuple(weights.shape), (3,))
        self.assertGreater(weights[2], weights[1])
        self.assertGreater(weights[1], weights[0])
        self.assertGreater(weights[2], 1.5)

    def test_compute_class_weights_keeps_absent_classes_at_zero_deterministically(self):
        train_dataset = {"labels": [0, 0, 1]}

        first = compute_class_weights(train_dataset, 4, class_weight_power=0.75)
        second = compute_class_weights(train_dataset, 4, class_weight_power=0.75)

        self.assertTrue(torch.equal(first, second))
        self.assertGreater(first[0], 0)
        self.assertGreater(first[1], 0)
        self.assertEqual(first[2], 0)
        self.assertEqual(first[3], 0)

    def test_configured_class_weight_power_is_explicit_and_validated(self):
        self.assertEqual(configured_class_weight_power({"class_weight_power": 0.5}), 0.5)

        with self.assertRaisesRegex(ValueError, "greater than zero"):
            configured_class_weight_power({"class_weight_power": 0})

    def test_create_trainer_passes_the_configured_exponent_to_weighting(self):
        configured = {**trainer_module.config, "class_weight_power": 0.5}
        callback = MagicMock()
        created_trainer = MagicMock()
        model = SimpleNamespace(config=SimpleNamespace(num_labels=3))

        with (
            patch.object(trainer_module, "config", configured),
            patch.object(trainer_module, "TrainingMetricsCallback", return_value=callback),
            patch.object(trainer_module, "TrainingArguments", return_value=MagicMock()),
            patch.object(trainer_module, "EarlyStoppingCallback", return_value=MagicMock()),
            patch.object(trainer_module, "EmotionTrainer", return_value=created_trainer),
            patch.object(
                trainer_module,
                "compute_class_weights",
                return_value=torch.ones(3),
            ) as compute_weights,
        ):
            trainer_module.create_trainer(
                model=model,
                tokenizer=MagicMock(),
                train_dataset={"labels": [0, 1, 2]},
                validation_dataset=MagicMock(),
            )

        self.assertEqual(compute_weights.call_args.kwargs["class_weight_power"], 0.5)


if __name__ == "__main__":
    unittest.main()
