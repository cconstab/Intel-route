#!/bin/bash
# Stop the live stack started by start_stack.sh
pkill -f "atsign.policy_engine" 2>/dev/null
pkill -f "planner_service.py" 2>/dev/null
pkill -f "planner_subscriber.py" 2>/dev/null    # legacy name
pkill -f "atsign.publishers" 2>/dev/null
pkill -f "atsign.operator_console" 2>/dev/null
pkill -f "policy_admin.dart" 2>/dev/null        # matches 'dart run' and the dartvm child
pkill -f "start_stack.sh" 2>/dev/null
echo "stack stopped"
