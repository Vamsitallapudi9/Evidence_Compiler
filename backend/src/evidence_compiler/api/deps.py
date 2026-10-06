from fastapi import Request

from evidence_compiler.app import AppContext


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx
