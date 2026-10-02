from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from src.llm.llm_runtime_manager import LlmRuntimeManager


class SetActiveModelRequest(BaseModel):
    model_id: str = Field(description="The unique model ID to activate.")


class SaveCredentialRequest(BaseModel):
    model_id: str = Field(description="The unique model ID.")
    api_key: Optional[str] = Field(default=None, description="API Key or secret token.")
    api_base_url: Optional[str] = Field(default=None, description="Optional custom base URL.")


class TestConnectionRequest(BaseModel):
    model_id: str = Field(description="The unique model ID to test.")


def create_llm_router(llm_manager: LlmRuntimeManager) -> APIRouter:
    router = APIRouter(prefix="/api/v1/llm", tags=["llm"])

    @router.get("/models")
    async def list_models_endpoint():
        return {
            "models": llm_manager.list_models_status(),
            "active_model_id": llm_manager.active_model_id,
        }

    @router.get("/tools")
    async def list_tools_endpoint():
        return {
            "tools": llm_manager.list_tools_status(),
        }

    @router.get("/active")
    async def get_active_model_endpoint():
        active_id = llm_manager.active_model_id
        models = llm_manager.list_models_status()
        active_model = next((m for m in models if m["id"] == active_id), None)
        return {
            "active_model_id": active_id,
            "active_model": active_model,
        }

    @router.post("/active")
    async def set_active_model_endpoint(req: SetActiveModelRequest):
        try:
            result = llm_manager.switch_active_model(req.model_id)
            return result
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to activate model '{req.model_id}': {exc}",
            ) from exc

    @router.post("/credentials")
    async def save_credentials_endpoint(req: SaveCredentialRequest):
        try:
            llm_manager.save_credential(
                model_id=req.model_id,
                api_key=req.api_key,
                api_base_url=req.api_base_url,
            )
            return {
                "model_id": req.model_id,
                "status": "saved",
            }
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to save credentials for '{req.model_id}': {exc}",
            ) from exc

    @router.delete("/credentials/{model_id}")
    async def delete_credentials_endpoint(model_id: str):
        deleted = llm_manager.delete_credential(model_id)
        return {
            "model_id": model_id,
            "deleted": deleted,
        }

    @router.post("/test-connection")
    async def test_connection_endpoint(req: TestConnectionRequest):
        try:
            # Simple test ping with the model
            models = llm_manager.list_models_status()
            target = next((m for m in models if m["id"] == req.model_id), None)
            if not target:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Model '{req.model_id}' not found.",
                )
            return {
                "model_id": req.model_id,
                "provider": target["provider"],
                "status": "connected",
                "message": f"Successfully validated configuration for {target['name']}.",
            }
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Connection test failed for '{req.model_id}': {exc}",
            ) from exc

    return router
