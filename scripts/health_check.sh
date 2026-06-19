#!/usr/bin/env bash
set -euo pipefail

# ╔══════════════════════════════════════════════════════════════╗
# ║  IKB v2.3 — Service Health Check                             ║
# ╚══════════════════════════════════════════════════════════════╝

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

PASS=0
FAIL=0
TOTAL=0

check_http() {
    local name="$1"
    local url="$2"
    local expected="${3:-healthy}"
    TOTAL=$((TOTAL + 1))

    printf "  %-30s " "${name}"
    if response=$(curl -sf --max-time 5 "$url" 2>/dev/null); then
        if echo "$response" | grep -qi "$expected"; then
            printf "${GREEN}✓ HEALTHY${NC}\n"
            PASS=$((PASS + 1))
        else
            printf "${YELLOW}⚠ UNEXPECTED RESPONSE${NC}\n"
            FAIL=$((FAIL + 1))
        fi
    else
        printf "${RED}✗ UNREACHABLE${NC}\n"
        FAIL=$((FAIL + 1))
    fi
}

check_tcp() {
    local name="$1"
    local host="$2"
    local port="$3"
    TOTAL=$((TOTAL + 1))

    printf "  %-30s " "${name}"
    if nc -z -w 3 "$host" "$port" 2>/dev/null || (echo > /dev/tcp/"$host"/"$port") 2>/dev/null; then
        printf "${GREEN}✓ REACHABLE${NC}\n"
        PASS=$((PASS + 1))
    else
        printf "${RED}✗ UNREACHABLE${NC}\n"
        FAIL=$((FAIL + 1))
    fi
}

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  IKB v2.3 — Service Health Check                         ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

echo "${CYAN}── Backend Services (3-service architecture) ──${NC}"
check_http "API Gateway :8000"         "http://localhost:8000/health"
check_http "Knowledge Engine :8001"    "http://localhost:8001/health"
check_http "Telemetry Aggregator :8002" "http://localhost:8002/health"
echo ""

echo "${CYAN}── Frontend ──${NC}"
check_http "Next.js Frontend :3000"    "http://localhost:3000" "Factory AI Brain"
echo ""

echo "${CYAN}── Data Stores ──${NC}"
check_tcp  "PostgreSQL/TimescaleDB"    "localhost" 5432
check_tcp  "Redis"                     "localhost" 6379
check_http "Qdrant"                    "http://localhost:6333/healthz" "ok"
check_tcp  "Neo4j (Bolt)"              "localhost" 7687
check_http "Neo4j (HTTP)"              "http://localhost:7474" ""
echo ""

echo "${CYAN}── Messaging ──${NC}"
check_tcp  "Kafka"                     "localhost" 9092
echo ""

echo "${CYAN}── Monitoring (optional) ──${NC}"
check_http "Prometheus"                "http://localhost:9090/-/healthy" "OK"
check_http "Grafana"                   "http://localhost:3001/api/health" "ok"
check_http "MLflow"                    "http://localhost:5000/health" ""
echo ""

echo "════════════════════════════════════════════════════════════"
printf "  Results: ${GREEN}%d passed${NC} / ${RED}%d failed${NC} / %d total\n" "$PASS" "$FAIL" "$TOTAL"
echo "════════════════════════════════════════════════════════════"
echo ""

if [ "$FAIL" -gt 0 ]; then
    echo "${RED}⚠  Some services are unhealthy. Check: make logs${NC}"
    exit 1
else
    echo "${GREEN}✅ All services are healthy!${NC}"
    exit 0
fi
