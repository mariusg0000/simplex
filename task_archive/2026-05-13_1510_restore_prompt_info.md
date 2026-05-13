# Restore important prompt info (work_dir, revisions, path requirements)

## Changes
- Restored {work_dir} workspace reference
- Restored REVISIONS section: read existing files with cat/ls, modify, regenerate
- Restored relative paths rule for writing files
- Restored absolute path requirement for task_done
- Restored revision support in agent_description (work_dir parameter)
- Kept: no fitz, no PDF reading, simple 3-step workflow
