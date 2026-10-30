"""Errors safe to show in the studio."""


class StudioError(Exception):
    def __init__(self, message, *, code="invalid_request", status=400, field=None):
        super().__init__(message)
        self.code, self.status, self.field = code, status, field

    def as_dict(self):
        return {"error": {"code": self.code, "message": str(self), "field": self.field}}
