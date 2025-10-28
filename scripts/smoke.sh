#!/bin/bash

# Trading Suite Smoke Test Script
# This script tests all services to ensure they are running correctly

set -e

echo "🚀 Starting Trading Suite Smoke Tests"
echo "====================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to test HTTP endpoint
test_endpoint() {
    local url=$1
    local service_name=$2
    local expected_status=${3:-200}
    
    echo -n "Testing $service_name... "
    
    response=$(curl -s -o /dev/null -w "%{http_code}" "$url" || echo "000")
    
    if [ "$response" = "$expected_status" ]; then
        echo -e "${GREEN}✓ PASS${NC} (HTTP $response)"
        return 0
    else
        echo -e "${RED}✗ FAIL${NC} (HTTP $response)"
        return 1
    fi
}

# Function to test service with timeout
test_service_with_timeout() {
    local url=$1
    local service_name=$2
    local timeout=${3:-10}
    
    echo -n "Testing $service_name (timeout: ${timeout}s)... "
    
    if timeout $timeout curl -s "$url" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ PASS${NC}"
        return 0
    else
        echo -e "${RED}✗ FAIL${NC} (timeout or error)"
        return 1
    fi
}

# Test results tracking
total_tests=0
passed_tests=0

# Test 1: Monolith Service
echo ""
echo "📊 Testing Monolith Service"
echo "---------------------------"
total_tests=$((total_tests + 1))
if test_endpoint "http://localhost:8000/health" "Monolith Health"; then
    passed_tests=$((passed_tests + 1))
fi

total_tests=$((total_tests + 1))
if test_endpoint "http://localhost:8000/symbols" "Monolith Symbols"; then
    passed_tests=$((passed_tests + 1))
fi

# Test 2: Strategy Services
echo ""
echo "🎯 Testing Strategy Services"
echo "-----------------------------"

services=("supertrend" "alphatrend" "ichimoku" "qqe_ssl_wae")
ports=(8101 8102 8103 8104)

for i in "${!services[@]}"; do
    service="${services[$i]}"
    port="${ports[$i]}"
    
    total_tests=$((total_tests + 1))
    if test_endpoint "http://localhost:$port/health" "$service Health"; then
        passed_tests=$((passed_tests + 1))
    fi
done

# Test 3: Orchestrator Service
echo ""
echo "🎛️  Testing Orchestrator Service"
echo "--------------------------------"
total_tests=$((total_tests + 1))
if test_endpoint "http://localhost:8200/health" "Orchestrator Health"; then
    passed_tests=$((passed_tests + 1))
fi

total_tests=$((total_tests + 1))
if test_endpoint "http://localhost:8200/services/status" "Orchestrator Service Status"; then
    passed_tests=$((passed_tests + 1))
fi

# Test 4: Dashboard Service
echo ""
echo "📈 Testing Dashboard Service"
echo "----------------------------"
total_tests=$((total_tests + 1))
if test_service_with_timeout "http://localhost:8300" "Dashboard" 15; then
    passed_tests=$((passed_tests + 1))
fi

# Test 5: Integration Test
echo ""
echo "🔗 Testing Integration"
echo "----------------------"

# Test getting a trading signal
echo -n "Testing trading signal generation... "
response=$(curl -s -X POST "http://localhost:8200/decide" \
    -H "Content-Type: application/json" \
    -d '{"symbol": "XAUUSD=X", "min_conf": 0.7}' \
    -w "%{http_code}" 2>/dev/null)

http_code="${response: -3}"
response_body="${response%???}"

if [ "$http_code" = "200" ]; then
    # Check if response contains expected fields
    if echo "$response_body" | grep -q '"decision"' && echo "$response_body" | grep -q '"confidence"'; then
        echo -e "${GREEN}✓ PASS${NC}"
        passed_tests=$((passed_tests + 1))
    else
        echo -e "${RED}✗ FAIL${NC} (invalid response format)"
    fi
else
    echo -e "${RED}✗ FAIL${NC} (HTTP $http_code)"
fi
total_tests=$((total_tests + 1))

# Test 6: Data Retrieval Test
echo ""
echo "📊 Testing Data Retrieval"
echo "-------------------------"
echo -n "Testing price data retrieval... "
response=$(curl -s "http://localhost:8000/prices?symbol=XAUUSD=X&start=2024-01-01" -w "%{http_code}" 2>/dev/null)

http_code="${response: -3}"
response_body="${response%???}"

if [ "$http_code" = "200" ]; then
    # Check if response contains price data
    if echo "$response_body" | grep -q '"data"' && echo "$response_body" | grep -q '"close"'; then
        echo -e "${GREEN}✓ PASS${NC}"
        passed_tests=$((passed_tests + 1))
    else
        echo -e "${RED}✗ FAIL${NC} (no price data)"
    fi
else
    echo -e "${RED}✗ FAIL${NC} (HTTP $http_code)"
fi
total_tests=$((total_tests + 1))

# Summary
echo ""
echo "📋 Test Summary"
echo "==============="
echo "Total Tests: $total_tests"
echo "Passed: $passed_tests"
echo "Failed: $((total_tests - passed_tests))"

if [ $passed_tests -eq $total_tests ]; then
    echo -e "${GREEN}🎉 All tests passed! Trading Suite is ready to go!${NC}"
    exit 0
else
    echo -e "${RED}❌ Some tests failed. Please check the services.${NC}"
    exit 1
fi
