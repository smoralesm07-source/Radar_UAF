from pathlib import Path

from radar_uaf.fusion_export import build as build_fusion_exports
from radar_uaf.pipeline import main


if __name__ == "__main__":
    main()
    print(build_fusion_exports(Path(__file__).resolve().parent))
