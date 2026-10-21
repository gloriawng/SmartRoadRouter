"""
Weather-Aware Routing Engine
Download road network and implement basic routing algorithms

Setup:
pip install osmnx networkx matplotlib folium pandas

Usage:
python day1_routing.py
"""

import osmnx as ox
import networkx as nx
import matplotlib.pyplot as plt
import folium
from typing import Tuple, List, Dict
import pickle
import heapq
from dataclasses import dataclass
from datetime import datetime

# ============================================================================
# STEP 1: Download and Save Road Network
# ============================================================================

def download_road_network(save_path: str = "ontario_roads.graphml"):
    """
    Download road network for Waterloo to Collingwood corridor.
    This covers the area you actually drive.
    
    Run this once, then load from file (much faster).
    """
    print("Downloading road network from OpenStreetMap...")
    print("This may take 2-3 minutes...")
    
    # Bounding box for Waterloo-Collingwood corridor
    # (north, south, west, east) format
    north, south = 44.5, 43.4
    east, west = -79.3, -80.6
    
    # Download the network
    G = ox.graph_from_bbox(
        north, south, east, west,
        network_type='drive',
        simplify=True  # Simplifies the graph (removes unnecessary nodes)
    )
    
    # Save to file
    ox.save_graphml(G, save_path)
    print(f"Road network saved to {save_path}")
    print(f"Nodes: {len(G.nodes)}, Edges: {len(G.edges)}")
    
    return G


def load_road_network(path: str = "ontario_roads.graphml"):
    """Load previously downloaded road network."""
    print(f"Loading road network from {path}...")
    G = ox.load_graphml(path)
    print(f"Loaded! Nodes: {len(G.nodes)}, Edges: {len(G.edges)}")
    return G


# ============================================================================
# STEP 2: Add Road Risk Properties
# ============================================================================

def add_risk_properties(G):
    """
    Enhance graph edges with risk-related properties.
    
    Properties we care about:
    - highway type (motorway > primary > secondary > residential > unclassified)
    - surface type (if available)
    - exposure (estimated from highway type)
    """
    
    # Highway type to risk multiplier mapping
    highway_risk = {
        'motorway': 1.0,       # Best maintained, plowed first
        'motorway_link': 1.1,
        'trunk': 1.1,
        'trunk_link': 1.2,
        'primary': 1.2,        # Main roads, well maintained
        'primary_link': 1.3,
        'secondary': 1.4,      # County roads, moderate maintenance
        'tertiary': 1.6,       # Local roads, less frequent plowing
        'unclassified': 2.0,   # Minor roads, minimal maintenance
        'residential': 1.8,
        'service': 2.2,
    }
    
    # Exposure estimation (open roads are worse in wind/snow)
    highway_exposure = {
        'motorway': 1.5,       # Often in open areas
        'trunk': 1.4,
        'primary': 1.3,
        'secondary': 1.2,
        'tertiary': 1.0,
        'unclassified': 0.9,
        'residential': 0.7,    # More sheltered
        'service': 0.6,
    }
    
    for u, v, key, data in G.edges(keys=True, data=True):
        # Get highway type
        highway = data.get('highway', 'unclassified')
        if isinstance(highway, list):
            highway = highway[0]  # Take first if multiple types
        
        # Add risk properties
        data['base_risk'] = highway_risk.get(highway, 1.5)
        data['exposure'] = highway_exposure.get(highway, 1.0)
        data['highway_type'] = highway
        
        # Add surface type if available (OSM sometimes has this)
        surface = data.get('surface', 'paved')
        data['surface'] = surface
        if surface in ['unpaved', 'gravel', 'dirt', 'compacted']:
            data['base_risk'] *= 1.8  # Unpaved roads are much worse
    
    print("Added risk properties to all edges")
    return G


# ============================================================================
# STEP 3: Implement Dijkstra's Algorithm
# ============================================================================

@dataclass
class WeatherCondition:
    """Weather parameters for route calculation."""
    snowfall_rate: float = 0.0  # cm/hour
    wind_speed: float = 0.0      # km/h
    temperature: float = 0.0     # Celsius
    
    def __repr__(self):
        return f"Snow:{self.snowfall_rate}cm/h Wind:{self.wind_speed}km/h Temp:{self.temperature}°C"


def calculate_edge_cost(G, u, v, key, weather: WeatherCondition, risk_aware: bool = True):
    """
    Calculate the cost of traversing an edge.
    
    Cost = base_travel_time * (1 + risk_factor)
    
    Risk factor depends on:
    - Road type (base_risk)
    - Weather conditions
    - Road exposure
    """
    data = G[u][v][key]
    
    # Base travel time (in seconds)
    length = data.get('length', 100)  # meters
    speed_limit = data.get('maxspeed', 50)  # km/h
    if isinstance(speed_limit, list):
        speed_limit = speed_limit[0]
    try:
        speed_limit = float(str(speed_limit).split()[0])  # Handle "50 km/h" strings
    except:
        speed_limit = 50
    
    base_time = (length / 1000) / speed_limit * 3600  # seconds
    
    if not risk_aware:
        return base_time  # Standard shortest-time routing
    
    # Calculate risk factor based on weather
    base_risk = data.get('base_risk', 1.5)
    exposure = data.get('exposure', 1.0)
    
    # Risk components
    snow_risk = weather.snowfall_rate * 0.3 * base_risk
    wind_risk = (weather.wind_speed / 50) * 0.2 * exposure
    freeze_risk = 0.1 if weather.temperature < 0 else 0
    
    risk_factor = snow_risk + wind_risk + freeze_risk
    
    # Cost = time * (1 + risk)
    cost = base_time * (1 + risk_factor)
    
    return cost


def dijkstra(G, start_node, end_node, weather: WeatherCondition, risk_aware: bool = True):
    """
    Dijkstra's algorithm for shortest path.
    
    Returns: (path, total_cost, stats)
    """
    # Priority queue: (cost, node, path)
    pq = [(0, start_node, [start_node])]
    visited = set()
    costs = {start_node: 0}
    
    while pq:
        current_cost, current_node, path = heapq.heappop(pq)
        
        if current_node in visited:
            continue
        
        visited.add(current_node)
        
        # Found destination
        if current_node == end_node:
            stats = {
                'total_cost': current_cost,
                'path_length': len(path),
                'nodes_explored': len(visited)
            }
            return path, current_cost, stats
        
        # Explore neighbors
        for neighbor in G.neighbors(current_node):
            if neighbor in visited:
                continue
            
            # Calculate edge cost (may be multiple edges between nodes)
            edge_costs = []
            for key in G[current_node][neighbor]:
                edge_cost = calculate_edge_cost(G, current_node, neighbor, key, weather, risk_aware)
                edge_costs.append(edge_cost)
            
            edge_cost = min(edge_costs)  # Take best edge if multiple
            new_cost = current_cost + edge_cost
            
            # Update if better path found
            if neighbor not in costs or new_cost < costs[neighbor]:
                costs[neighbor] = new_cost
                new_path = path + [neighbor]
                heapq.heappush(pq, (new_cost, neighbor, new_path))
    
    return None, float('inf'), {'error': 'No path found'}


# ============================================================================
# STEP 4: Visualization
# ============================================================================

def visualize_routes(G, routes_dict: Dict[str, List], save_path: str = "route_comparison.html"):
    """
    Visualize multiple routes on an interactive map.
    
    routes_dict: {route_name: node_list}
    """
    # Get center point for map
    lats = [G.nodes[node]['y'] for route in routes_dict.values() for node in route]
    lons = [G.nodes[node]['x'] for route in routes_dict.values() for node in route]
    center_lat = sum(lats) / len(lats)
    center_lon = sum(lons) / len(lons)
    
    # Create map
    m = folium.Map(location=[center_lat, center_lon], zoom_start=10)
    
    # Colors for different routes
    colors = ['blue', 'red', 'green', 'purple', 'orange']
    
    for idx, (route_name, nodes) in enumerate(routes_dict.items()):
        # Get coordinates
        coords = [(G.nodes[node]['y'], G.nodes[node]['x']) for node in nodes]
        
        # Add route to map
        folium.PolyLine(
            coords,
            color=colors[idx % len(colors)],
            weight=4,
            opacity=0.7,
            popup=route_name
        ).add_to(m)
        
        # Add start/end markers
        folium.Marker(
            coords[0],
            popup=f"{route_name} - Start",
            icon=folium.Icon(color=colors[idx % len(colors)], icon='play')
        ).add_to(m)
        
        folium.Marker(
            coords[-1],
            popup=f"{route_name} - End",
            icon=folium.Icon(color=colors[idx % len(colors)], icon='stop')
        ).add_to(m)
    
    # Save
    m.save(save_path)
    print(f"Map saved to {save_path}")
    return m


# ============================================================================
# STEP 5: Main Demo
# ============================================================================

def main():
    """Run complete demo."""
    
    print("="*60)
    print("WEATHER-AWARE ROUTING ENGINE - DAY 1 DEMO")
    print("="*60)
    
    # Load or download network
    try:
        G = load_road_network()
    except FileNotFoundError:
        print("Road network not found. Downloading...")
        G = download_road_network()
    
    # Add risk properties
    G = add_risk_properties(G)
    
    # Define test route (Waterloo to Collingwood area)
    # You'll need to find actual node IDs near your start/end points
    # For now, let's find nodes near specific coordinates
    
    # Waterloo area (approximate)
    start_point = (43.4643, -80.5204)
    # Collingwood area (approximate)
    end_point = (44.5011, -80.2169)
    
    print(f"\nFinding nearest nodes to start/end points...")
    start_node = ox.distance.nearest_nodes(G, start_point[1], start_point[0])
    end_node = ox.distance.nearest_nodes(G, end_point[1], end_point[0])
    
    print(f"Start node: {start_node}")
    print(f"End node: {end_node}")
    
    # Test scenarios
    print("\n" + "="*60)
    print("SCENARIO 1: Good Weather (Baseline)")
    print("="*60)
    good_weather = WeatherCondition(snowfall_rate=0, wind_speed=10, temperature=5)
    print(f"Weather: {good_weather}")
    
    path_good, cost_good, stats_good = dijkstra(G, start_node, end_node, good_weather, risk_aware=False)
    print(f"Route found: {stats_good['path_length']} nodes, Cost: {cost_good:.1f}s ({cost_good/60:.1f} min)")
    
    # Calculate total distance
    total_distance = sum(
        G[path_good[i]][path_good[i+1]][0].get('length', 0) 
        for i in range(len(path_good)-1)
    ) / 1000
    print(f"Total distance: {total_distance:.1f} km")
    
    print("\n" + "="*60)
    print("SCENARIO 2: Bad Weather - Standard Routing (Risk-Unaware)")
    print("="*60)
    bad_weather = WeatherCondition(snowfall_rate=5, wind_speed=60, temperature=-10)
    print(f"Weather: {bad_weather}")
    
    path_bad_standard, cost_bad_standard, stats_bad_standard = dijkstra(
        G, start_node, end_node, bad_weather, risk_aware=False
    )
    print(f"Route found: {stats_bad_standard['path_length']} nodes, Cost: {cost_bad_standard:.1f}s ({cost_bad_standard/60:.1f} min)")
    
    print("\n" + "="*60)
    print("SCENARIO 3: Bad Weather - Risk-Aware Routing")
    print("="*60)
    print(f"Weather: {bad_weather}")
    
    path_bad_aware, cost_bad_aware, stats_bad_aware = dijkstra(
        G, start_node, end_node, bad_weather, risk_aware=True
    )
    print(f"Route found: {stats_bad_aware['path_length']} nodes, Cost: {cost_bad_aware:.1f}s ({cost_bad_aware/60:.1f} min)")
    
    # Calculate distance for risk-aware route
    total_distance_aware = sum(
        G[path_bad_aware[i]][path_bad_aware[i+1]][0].get('length', 0) 
        for i in range(len(path_bad_aware)-1)
    ) / 1000
    print(f"Total distance: {total_distance_aware:.1f} km")
    
    # Comparison
    print("\n" + "="*60)
    print("COMPARISON")
    print("="*60)
    print(f"Distance increase: {((total_distance_aware - total_distance) / total_distance * 100):.1f}%")
    print(f"Time increase (good weather): {((cost_bad_aware - cost_good) / cost_good * 100):.1f}%")
    print(f"Risk reduction: Routes differ by {abs(len(path_bad_aware) - len(path_bad_standard))} nodes")
    
    # Visualize
    print("\nGenerating visualization...")
    routes = {
        'Good Weather (Shortest Path)': path_good,
        'Bad Weather (Risk-Unaware)': path_bad_standard,
        'Bad Weather (Risk-Aware)': path_bad_aware
    }
    visualize_routes(G, routes)
    
    print("\n" + "="*60)
    print("DONE! Check route_comparison.html in your browser")
    print("="*60)
    
    # Save graph for later use
    with open('processed_graph.pkl', 'wb') as f:
        pickle.dump(G, f)
    print("Processed graph saved to processed_graph.pkl")


if __name__ == "__main__":
    main()