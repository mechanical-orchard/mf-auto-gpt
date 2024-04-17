import glob
import pathlib

import os

from forge.actions import action

mainframe_files = os.environ["FILES_SRC_PATH"]


files = {}
# do not include files starting with a dot
for item in glob.glob(f"{mainframe_files}/**/[!.]*", recursive=True):
    if not os.path.isdir(item):
        basename = os.path.basename(item)
        relative_path = os.path.dirname(os.path.relpath(item, mainframe_files))
        with open(item, mode="rb") as f:
            content = f.read()
        file_name = pathlib.Path(basename).stem
        files[file_name] = content.decode("iso-8859-1)")

@action(
    name="load_source_by_name",
    description="Loads the source of a specific file",
    parameters=[
        {
            "name": "file_name",
            "description": "The name of the file",
            "type": "string",
            "required": True,
        }
    ],
    output_type="list[str]",
)
async def load_source_by_name(agent, task_id: str, file_name: str) -> str:
    """
    Returns the source code of the specified file, if available.
    """
    if file_name in files:
        content = files[file_name]
        return [content]
    else:
        return ["File not found."]
