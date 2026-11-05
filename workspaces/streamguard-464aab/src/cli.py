#!/usr/bin/env python3
"""CLI Interface for AgentHive Project."""
import argparse
import sys
import json
from .engine import CoreEngine

def main():
    parser = argparse.ArgumentParser(description='AgentHive Verified Application')
    parser.add_argument('--action', choices=['run', 'status', 'test'], default='run')
    parser.add_argument('--payload', type=str, default='{}')
    args = parser.parse_args()
    engine = CoreEngine()
    res = engine.process(args.action, args.payload)
    print(json.dumps(res, indent=2))
    return 0

if __name__ == '__main__':
    sys.exit(main())
