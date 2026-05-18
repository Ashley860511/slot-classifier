import importlib
import sys


MODULES = ["numpy", "cv2", "paddle", "paddleocr"]


def version_of(module):
    return getattr(module, "__version__", "unknown")


def main():
    print(f"Python executable: {sys.executable}")
    print(f"Python version: {sys.version.split()[0]}")
    ok = True

    loaded = {}
    for name in MODULES:
        try:
            module = importlib.import_module(name)
            loaded[name] = module
            print(f"OK   {name}: {version_of(module)}")
        except Exception as exc:
            ok = False
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")

    numpy = loaded.get("numpy")
    cv2 = loaded.get("cv2")
    if numpy is not None and cv2 is not None:
        numpy_version = version_of(numpy)
        cv2_version = version_of(cv2)
        if numpy_version.startswith("2.") and cv2_version.startswith("4.6."):
            ok = False
            print("FAIL compatibility: OpenCV 4.6.x is not compatible with NumPy 2.x in this environment.")
            print("Fix: install numpy==1.26.4, or upgrade OpenCV to a NumPy-2-compatible build.")

    if ok:
        print("Environment check passed. main.py should be able to start.")
        return 0

    print("\nRecommended clean install:")
    print("  python -m venv .venv")
    print("  .\\.venv\\Scripts\\Activate.ps1")
    print("  python -m pip install --upgrade pip")
    print("  python -m pip install -r requirements.txt")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
