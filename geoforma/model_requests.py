"""Detach model inputs without copying desktop review sessions or candidate histories."""
import copy


def model_image(image):
    return copy.deepcopy({k:v for k,v in image.items() if k not in ('working_draft','mode_sessions','candidate_runs','dismissed_candidates','_reference')})
