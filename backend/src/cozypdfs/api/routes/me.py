from fastapi import APIRouter, Depends

from cozypdfs.api.deps import get_current_owner_id

router = APIRouter(tags=["identity"])


@router.get("/me")
def me(owner_id: str = Depends(get_current_owner_id)) -> dict:
    return {"identity_id": owner_id}
