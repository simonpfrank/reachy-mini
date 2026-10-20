"""Shared building blocks for the robot tools. Not tools themselves.

The app only treats top-level ``*.py`` files in this folder as tools, so this subfolder is never loaded as one.
A tool reaches it by adding its own folder to ``sys.path`` first (the app loads tools by file path and does not):

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from reachy_lib import motion
"""
