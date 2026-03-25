import os
import re

# Mapping of OLD import patterns to NEW import patterns
REPLACEMENTS = {
    r'from stockguru_agents\.models': 'from src.agents.models',
    r'import stockguru_agents\.models': 'import src.agents.models',
    r'from stockguru_agents\.broker_connector': 'from src.agents.broker_connector',
    r'from stockguru_agents\.feeds': 'from src.agents.feeds',
    r'from stockguru_agents\.sovereign': 'from src.agents.sovereign',
    r'from stockguru_agents\.atlas': 'from src.agents.atlas',
    r'from conviction_filter import': 'from src.core.conviction_filter import',
    r'from orchestrator import': 'from src.agents.orchestrator import',
    r'from learning import': 'from src.agents.learning import',
    r'from channels import': 'from src.agents.channels import',
    r'from backtesting import': 'from src.agents.backtesting import',
    r'from connectors import': 'from src.agents.connectors import',
    r'from agents import': 'from src.agents import',
    r'from sovereign import': 'from src.agents.sovereign import',
}

TARGET_DIRS = ['src', 'tests', 'scripts']

def repair_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_content = content
    for pattern, replacement in REPLACEMENTS.items():
        content = re.sub(pattern, replacement, content)
    
    if content != original_content:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✅ Repaired: {file_path}")

def run_repair():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    for target in TARGET_DIRS:
        target_path = os.path.join(root_dir, target)
        if not os.path.exists(target_path):
            continue
            
        for root, dirs, files in os.walk(target_path):
            for file in files:
                if file.endswith('.py'):
                    repair_file(os.path.join(root, file))

if __name__ == "__main__":
    run_repair()
    print("🚀 Global Import Repair Complete!")
