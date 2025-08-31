import asyncio
import threading
import requests
import time
from kivy.uix.boxlayout import BoxLayout
from kivy.properties import StringProperty, BooleanProperty, NumericProperty, ObjectProperty, ListProperty
from kivy.clock import Clock
from kivy.lang import Builder
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout
from kivy.metrics import dp

# Load the KV string for MonitorTab
Builder.load_file('views/monitor_tab.kv')

class MonitorTab(BoxLayout):
    """
    A tab for monitoring the state of Lily Core and related services.
    """
    
    # Connection status properties
    connection_status = StringProperty("Unknown")
    is_connected = BooleanProperty(False)
    
    # Service statuses
    lily_core_status = StringProperty("Unknown")
    tts_provider_status = StringProperty("Unknown")
    web_scout_status = StringProperty("Unknown")
    
    # Service health indicators
    lily_core_healthy = BooleanProperty(False)
    tts_provider_healthy = BooleanProperty(False)
    web_scout_healthy = BooleanProperty(False)
    
    # Recent events
    recent_events = ListProperty([])
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.padding = [dp(10), dp(10), dp(10), dp(10)]
        self.spacing = dp(10)
        
        # Schedule initialization
        Clock.schedule_once(self._post_init)
        
    def _post_init(self, dt):
        """Initialize UI components after KV is loaded."""
        print("MonitorTab: Post-initialization...")
        
        # Start monitoring in background
        threading.Thread(target=self._start_monitoring, daemon=True).start()
        
    def _start_monitoring(self):
        """Start monitoring all services in background."""
        # Start monitoring all services
        self._monitor_services()
        
    def _monitor_services(self):
        """Monitor all services in background."""
        while True:
            try:
                # Fetch Lily Core status
                lily_core_data = self._fetch_lily_core_status()
                
                # Fetch TTS Provider status
                tts_provider_data = self._fetch_tts_provider_status()
                
                # Fetch Web Scout status
                web_scout_data = self._fetch_web_scout_status()
                
                # Update UI on main thread
                Clock.schedule_once(lambda dt: self._update_service_statuses(
                    lily_core_data,
                    tts_provider_data,
                    web_scout_data
                ))
                
                # Add events based on status changes
                self._add_status_events(lily_core_data, tts_provider_data, web_scout_data)
                
            except Exception as e:
                print(f"MonitorTab: Error monitoring services: {e}")
                Clock.schedule_once(lambda dt: self._add_event(f"Monitoring error: {str(e)}"))
            
            # Wait before next update
            time.sleep(10)  # Check every 10 seconds
            
    def _add_event(self, event):
        """Add a new event to the recent events list."""
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        event_text = f"[{timestamp}] {event}"
        
        self.recent_events.append(event_text)
        
        # Keep only the last 50 events
        if len(self.recent_events) > 50:
            self.recent_events = self.recent_events[-50:]
            
    def refresh_data(self):
        """Manually refresh monitoring data."""
        print("MonitorTab: Refreshing data...")
        # Trigger an immediate update
        threading.Thread(target=self._refresh_once, daemon=True).start()
        
    def _refresh_once(self):
        """Refresh data once in background."""
        try:
            # Fetch all service statuses
            lily_core_data = self._fetch_lily_core_status()
            tts_provider_data = self._fetch_tts_provider_status()
            web_scout_data = self._fetch_web_scout_status()
            
            # Update UI on main thread
            Clock.schedule_once(lambda dt: self._update_service_statuses(
                lily_core_data,
                tts_provider_data,
                web_scout_data
            ))
            
            # Add events based on status changes
            self._add_status_events(lily_core_data, tts_provider_data, web_scout_data)
            
        except Exception as e:
            print(f"MonitorTab: Error refreshing data: {e}")
            Clock.schedule_once(lambda dt: self._add_event(f"Refresh error: {str(e)}"))
        
    def _fetch_lily_core_status(self):
        """Fetch Lily Core monitoring status."""
        try:
            # Default URLs - in a real implementation, these would come from config
            lily_core_url = "http://localhost:8000/monitoring"
            
            response = requests.get(lily_core_url, timeout=5)
            if response.status_code == 200:
                return response.json()
            else:
                return {"status": "error", "details": f"HTTP {response.status_code}"}
        except Exception as e:
            return {"status": "down", "details": str(e)}
            
    def _fetch_tts_provider_status(self):
        """Fetch TTS Provider monitoring status through Lily Core."""
        # Get status from Lily Core which aggregates all service statuses
        lily_core_data = self._fetch_lily_core_status()
        
        # Extract TTS Provider status from Lily Core data
        if "services" in lily_core_data:
            for service in lily_core_data["services"]:
                if service.get("name") == "TTS-Provider":
                    return service
        
        # If not found, return unknown status
        return {"status": "unknown", "details": "Service status not available through Lily Core"}
            
    def _fetch_web_scout_status(self):
        """Fetch Web Scout monitoring status through Lily Core."""
        # Get status from Lily Core which aggregates all service statuses
        lily_core_data = self._fetch_lily_core_status()
        
        # Extract Web Scout status from Lily Core data
        if "services" in lily_core_data:
            for service in lily_core_data["services"]:
                if service.get("name") == "Web-Scout":
                    return service
        
        # If not found, return unknown status
        return {"status": "unknown", "details": "Service status not available through Lily Core"}
            
    def _update_service_statuses(self, lily_core_data, tts_provider_data, web_scout_data):
        """Update service statuses on the UI."""
        # Update Lily Core status
        lily_core_status = lily_core_data.get("status", "unknown")
        self.lily_core_status = lily_core_status.capitalize()
        self.lily_core_healthy = lily_core_status == "healthy"
        
        # Update TTS Provider status
        tts_provider_status = tts_provider_data.get("status", "unknown")
        self.tts_provider_status = tts_provider_status.capitalize()
        self.tts_provider_healthy = tts_provider_status == "healthy"
        
        # Update Web Scout status
        web_scout_status = web_scout_data.get("status", "unknown")
        self.web_scout_status = web_scout_status.capitalize()
        self.web_scout_healthy = web_scout_status == "healthy"
        
        # Update overall connection status
        if lily_core_status == "healthy" and tts_provider_status == "healthy" and web_scout_status == "healthy":
            self.connection_status = "All Services Healthy"
            self.is_connected = True
        elif lily_core_status == "healthy":
            self.connection_status = "Lily Core Connected"
            self.is_connected = True
        else:
            self.connection_status = "Disconnected"
            self.is_connected = False
        
    def _add_status_events(self, lily_core_data, tts_provider_data, web_scout_data):
        """Add events based on service status changes."""
        # Add events for any service that is not healthy
        if lily_core_data.get("status") != "healthy":
            status = lily_core_data.get("status", "unknown")
            details = lily_core_data.get("details", "")
            self._add_event(f"Lily Core status: {status} - {details}")
            
        if tts_provider_data.get("status") != "healthy":
            status = tts_provider_data.get("status", "unknown")
            details = tts_provider_data.get("details", "")
            self._add_event(f"TTS Provider status: {status} - {details}")
            
        if web_scout_data.get("status") != "healthy":
            status = web_scout_data.get("status", "unknown")
            details = web_scout_data.get("details", "")
            self._add_event(f"Web Scout status: {status} - {details}")
            
        # Add events for healthy services
        if lily_core_data.get("status") == "healthy" and not hasattr(self, '_lily_core_healthy_logged'):
            self._add_event("Lily Core is healthy")
            self._lily_core_healthy_logged = True
        elif lily_core_data.get("status") != "healthy":
            self._lily_core_healthy_logged = False
            
        if tts_provider_data.get("status") == "healthy" and not hasattr(self, '_tts_provider_healthy_logged'):
            self._add_event("TTS Provider is healthy")
            self._tts_provider_healthy_logged = True
        elif tts_provider_data.get("status") != "healthy":
            self._tts_provider_healthy_logged = False
            
        if web_scout_data.get("status") == "healthy" and not hasattr(self, '_web_scout_healthy_logged'):
            self._add_event("Web Scout is healthy")
            self._web_scout_healthy_logged = True
        elif web_scout_data.get("status") != "healthy":
            self._web_scout_healthy_logged = False