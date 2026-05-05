---
description: "Runs a strict Principal Engineer level architectural review on a feature spec."
parameters:
  - name: spec_file
    description: "The path to the markdown spec file you want to review (e.g., docs/features/01_payload_contracts.md)"
    required: true
---

Read the Spec Reviewer system prompt instructions from `docs/spec_reviewer.md`. 
Then, read and analyze the feature specification file located at: `{{spec_file}}`.

Execute all 7 steps of the review against that spec. Output the complete review using the strict Output Template defined in the instructions. Do not skip any section. Be ruthless.