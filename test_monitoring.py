#!/usr/bin/env python3
"""
Test script for monitoring endpoints
"""

import requests
import time

def test_lily_core_monitoring():
    """Test Lily Core monitoring endpoint."""
    try:
        response = requests.get("http://localhost:8000/monitoring", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print("✅ Lily Core Monitoring Test Passed")
            print(f"   Status: {data.get('status')}")
            print(f"   Service: {data.get('service_name')}")
            metrics = data.get('metrics', {})
            if metrics:
                print(f"   CPU Usage: {metrics.get('cpu_usage', 'N/A')}%")
                print(f"   Memory Usage: {metrics.get('memory_usage', 'N/A')}%")
            return True
        else:
            print(f"❌ Lily Core Monitoring Test Failed: HTTP {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Lily Core Monitoring Test Failed: {e}")
        return False

def test_tts_provider_monitoring():
    """Test TTS Provider monitoring endpoint through Lily Core."""
    try:
        # Get TTS Provider status through Lily Core
        response = requests.get("http://localhost:8000/monitoring", timeout=5)
        if response.status_code == 200:
            data = response.json()
            # Extract TTS Provider status from services list
            tts_status = None
            if "services" in data:
                for service in data["services"]:
                    if service.get("name") == "TTS-Provider":
                        tts_status = service
                        break
            
            if tts_status:
                print("✅ TTS Provider Monitoring Test Passed")
                print(f"   Status: {tts_status.get('status')}")
                print(f"   Service: TTS-Provider")
                return True
            else:
                print("❌ TTS Provider Monitoring Test Failed: Service not found in Lily Core response")
                return False
        else:
            print(f"❌ TTS Provider Monitoring Test Failed: HTTP {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ TTS Provider Monitoring Test Failed: {e}")
        return False

def test_web_scout_monitoring():
    """Test Web Scout monitoring endpoint through Lily Core."""
    try:
        # Get Web Scout status through Lily Core
        response = requests.get("http://localhost:8000/monitoring", timeout=5)
        if response.status_code == 200:
            data = response.json()
            # Extract Web Scout status from services list
            web_scout_status = None
            if "services" in data:
                for service in data["services"]:
                    if service.get("name") == "Web-Scout":
                        web_scout_status = service
                        break
            
            if web_scout_status:
                print("✅ Web Scout Monitoring Test Passed")
                print(f"   Status: {web_scout_status.get('status')}")
                print(f"   Service: Web-Scout")
                return True
            else:
                print("❌ Web Scout Monitoring Test Failed: Service not found in Lily Core response")
                return False
        else:
            print(f"❌ Web Scout Monitoring Test Failed: HTTP {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Web Scout Monitoring Test Failed: {e}")
        return False

def main():
    """Run all monitoring tests."""
    print("Running Monitoring Tests...\n")
    
    tests = [
        test_lily_core_monitoring,
        test_tts_provider_monitoring,
        test_web_scout_monitoring
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        print()  # Add spacing between tests
    
    print(f"Monitoring Tests Summary: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All monitoring tests passed!")
    else:
        print("⚠️  Some monitoring tests failed. Please check the services.")

if __name__ == "__main__":
    main()