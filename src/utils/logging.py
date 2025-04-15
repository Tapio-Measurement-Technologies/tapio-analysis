import time
import platform
from datetime import datetime
import sys
import settings

launch_time = time.time()

def get_platform_info_header():
    uptime_sec = int(time.time() - launch_time)
    uptime_str = f"{uptime_sec // 60}m {uptime_sec % 60}s"
    cli_args = " ".join(sys.argv)

    # Include all UPPERCASE variables from settings
    from inspect import ismodule
    setting_lines = [
        f"{key:30}: {getattr(settings, key)}"
        for key in dir(settings)
        if key.isupper() and not key.startswith("_") and not ismodule(getattr(settings, key))
    ]

    header = [
        "==== Platform Info ====",
        f"Exported at               : {datetime.now().isoformat()}",
        f"OS                        : {platform.system()} {platform.release()}",
        f"Python Version            : {platform.python_version()}",
        f"Uptime                    : {uptime_str}",
        f"Command-line Arguments    : {cli_args}\n",
        "--- Settings ---"
    ] + setting_lines + ["========================"]

    return "\n".join(header)