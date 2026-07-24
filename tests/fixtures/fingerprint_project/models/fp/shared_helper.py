"""Not a model -- a plain project-local helper imported by py_model_1.py and
py_model_2.py. Used to exercise #13 acceptance criterion 7 (shared-import
detection): editing this file must change both importing models'
fingerprints, even though neither model's own source changed."""

GREETING = "hello"
