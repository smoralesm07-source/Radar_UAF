from pathlib import Path

from radar_uaf.entity_typing_v11 import apply_entity_typing
from radar_uaf.fusion_export import build as build_fusion_exports
from radar_uaf.pipeline import main


if __name__ == "__main__":
    main()
    root = Path(__file__).resolve().parent
    print(build_fusion_exports(root))
    print(apply_entity_typing(root))
