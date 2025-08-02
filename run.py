import importlib
import os
import json

if __name__ == "__main__":
    print("start stock analysis system ...")
    
    # check dependencies
    missing_deps = []
    required_deps = [
        "akshare",
        "pandas",
        "flask",
        "flask_cors",
        "openai"
    ]
    
    for dep in required_deps:
        try:
            importlib.import_module(dep)
        except ImportError:
            missing_deps.append(dep)
            print(f"{dep} not installed")
        
    if missing_deps:
        print(f"lack of necessary dependencies: {', '.join(missing_deps)}")
        exit(0)
        
    
    
    