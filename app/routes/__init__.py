from fastapi import APIRouter
from .upload import router as upload_router
from .status import router as status_router
from .group_members import router as group_members_router
from .groups import router as groups_router
from .meetings import router as meetings_router
from .users import router as users_router

router = APIRouter()
router.include_router(upload_router)
router.include_router(status_router)
router.include_router(group_members_router)
router.include_router(groups_router)
router.include_router(meetings_router)
router.include_router(users_router)
