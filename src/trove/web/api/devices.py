from __future__ import annotations

from fastapi import APIRouter, Request, Response

from trove.errors import DeviceNotFoundError
from trove.web.deps import runtime
from trove.web.schemas import DeviceListResponse

router = APIRouter()


@router.get("/devices", response_model=DeviceListResponse)
def api_devices(request: Request):
    devices = runtime(request).devices.list()
    return {
        "devices": [
            {
                "device_id": device.device_id,
                "name": device.name,
                "created_at": device.created_at,
                "last_used_at": device.last_used_at,
                "revoked_at": device.revoked_at,
            }
            for device in devices
        ]
    }


@router.delete("/devices/{device_id}", status_code=204)
def api_revoke_device(request: Request, device_id: str):
    if runtime(request).devices.revoke(device_id) is None:
        raise DeviceNotFoundError("Device not found")
    return Response(status_code=204)
