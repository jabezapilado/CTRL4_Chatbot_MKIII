# English Emotion Recognition Model — v10 Provenance

## Scope

This record documents the externally provisioned English emotion-model artifact
used by CTRL4 Chatbot MK III. It is a curated provenance record, not a copy of
the model binary or generated evaluation tree.

## Runtime relationship

- **Model version:** `v10`
- **Runtime relationship:** v10 is the source model for the deployed
  `ai_engine/models/english/latest` directory.
- **Alias rule:** `latest` is a deployment alias of v10, not a separately
  trained model.
- **Runtime artifact filename:** `model.safetensors`
- **External-artifact policy:** the model binary is provisioned outside normal
  Git history and verified before deployment.

## Verified runtime artifact

| Field | Verified value |
| --- | --- |
| Runtime artifact SHA-256 | `d90161c6b064d42ecee866e099f9f3125abb969e7a5ce76cd4c4fb32369ccce9` |
| Expected artifact size | `267841796` bytes |
| Runtime manifest | [runtime_artifact_manifest.json](../../../../ai_engine/models/english/latest/runtime_artifact_manifest.json) |
| Verification date | 2026-08-05 |

The checksum and expected size are taken from the committed runtime artifact
manifest. The local v10 and `english/latest` model weights had the same
SHA-256 during the 2026-08-05 provenance audit.

## Training evidence

- **Base model:** `distilbert-base-uncased`
- **Prediction taxonomy:** five classes defined by
  `ai_engine/configs/label_encoder.json`.
- **Dataset source summary:** merged GoEmotions, ISEAR, and DAIR-AI Emotion
  records, as documented in `docs/emotion_label_lineage_report.md`.
- **Dataset release/version:** unavailable from immutable repository evidence.
- **Training-configuration artifact:** the local v10 `training_args.bin` had
  SHA-256 `c3fd99feb5695e83b22f9941e9030dc3de1568c3f3bd22188e1bcb3ca025e37f`.
  It remains an external training artifact and is not committed.
- **Training configuration file hash:** unavailable. The repository did not
  preserve an immutable copy of `model_config.json` for the v10 run.

## Evaluation evidence

- **Checkpoint validation best metric:** `0.7950942302284574`, recorded by the
  local v10 checkpoint metadata.
- **Held-out evaluation summary:** unavailable as immutable provenance. The
  previous shared generated evaluation tree was not version-isolated and is
  intentionally not used as v10 evidence.
- **Evaluation artifact hash:** unavailable until a version-isolated v10
  evaluation run is produced through the corrected publication workflow.

## Reproduction boundary

Training assets, checkpoints, optimizer state, scheduler state, random-number
state, and generated metrics remain external or local. A future reproduction
run must generate a fresh version-specific evaluation directory before any
documentation alias is published.
