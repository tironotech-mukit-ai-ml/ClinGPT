#!/bin/bash
# Test CORS configuration on the server

echo "Testing CORS for EMR AI Integration"
echo "====================================="
echo ""

# Test from server IP (what browser sees)
echo "TEST 1: CORS preflight from server IP (159.198.76.203:8005)"
curl -v \
  -H "Origin: http://159.198.76.203:8005" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: Content-Type" \
  -X OPTIONS \
  http://localhost:8001/api/v1/clin-gpt/emr-analysis/ 2>&1 | grep -i "access-control"

echo ""
echo "TEST 2: CORS preflight from port 8000"
curl -v \
  -H "Origin: http://159.198.76.203:8000" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: Content-Type" \
  -X OPTIONS \
  http://localhost:8001/api/v1/clin-gpt/emr-analysis/ 2>&1 | grep -i "access-control"

echo ""
echo "TEST 3: Actual POST request from server IP"
curl -X POST \
  -H "Origin: http://159.198.76.203:8005" \
  -H "Content-Type: application/json" \
  -d '{"age": 45, "gender": "Male", "cc": "Test"}' \
  http://localhost:8001/api/v1/clin-gpt/emr-analysis/ 2>&1 | head -10

echo ""
echo "If you see 'Access-Control-Allow-Origin' headers above, CORS is working!"
echo "Expected header: Access-Control-Allow-Origin: http://159.198.76.203:8005"
