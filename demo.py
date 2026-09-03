"""
demo.py -- runs all three analyst agents against the illustrative sample
warehouse (see build_sample_data.py). No real business data required.

    pip install -r requirements.txt
    python build_sample_data.py
    python demo.py
"""
from margin_erosion_agent import run_margin_erosion_check
from stockout_prevention_agent import run_stockout_prevention_agent
from markdown_optimization_agent import run_markdown_optimization_agent

if __name__ == "__main__":
    print("### Margin Erosion Agent ###\n")
    run_margin_erosion_check()
    print("\n### Stockout Prevention Agent ###\n")
    run_stockout_prevention_agent()
    print("\n### Markdown Optimization Agent ###\n")
    run_markdown_optimization_agent()

