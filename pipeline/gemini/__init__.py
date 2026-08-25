# Flat sibling imports throughout this package (e.g. `from models import X`)
# resolve because whatever entry point launched the process -- worker.py,
# cli.py -- lives directly in pipeline/, putting pipeline/ on sys.path.
# Modules in here are library code only, never run directly, so this always
# holds; don't `cd pipeline/gemini && python analyze.py`, it won't resolve.
