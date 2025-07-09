from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter()

@router.get("/ui", response_class=FileResponse, summary="Serve the main HTML user interface", tags=['AI'])
async def read_root():
    """
    This endpoint serves the main HTML page which contains the user interface
    for interacting with the API.
    """
    return "templates/index.html"
