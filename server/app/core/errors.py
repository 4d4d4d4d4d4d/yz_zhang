from fastapi import HTTPException


def bad_request(message: str, code: str = "bad_request") -> HTTPException:
    return HTTPException(status_code=400, detail={"code": code, "message": message})


def forbidden(message: str = "无权操作", code: str = "forbidden") -> HTTPException:
    return HTTPException(status_code=403, detail={"code": code, "message": message})


def not_found(message: str = "资源不存在", code: str = "not_found") -> HTTPException:
    return HTTPException(status_code=404, detail={"code": code, "message": message})


def conflict(message: str, code: str = "conflict") -> HTTPException:
    return HTTPException(status_code=409, detail={"code": code, "message": message})


def too_many_requests(message: str, code: str = "rate_limited", retry_after: int = 60,
                      headers: dict[str, str] | None = None) -> HTTPException:
    """API-050（145 号 spec）真正的 429：带 Retry-After，集成方的 HTTP 客户端认得出该退避。"""
    return HTTPException(status_code=429, detail={"code": code, "message": message},
                         headers={"Retry-After": str(retry_after), **(headers or {})})
