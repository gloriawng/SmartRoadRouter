import * as Location from "expo-location";
import { StatusBar } from "expo-status-bar";
import { useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Linking,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

type Place = {
  label: string;
  latitude: number;
  longitude: number;
};

type WeatherObservation = {
  provider: string;
  time: string | null;
  temperature_c: number | null;
  feels_like_c: number | null;
  precipitation_mm: number | null;
  snowfall_cm: number | null;
  weather_code: number | null;
  wind_kmh: number | null;
  wind_gusts_kmh: number | null;
};

type Route = {
  provider: string;
  distance_km: number;
  duration_minutes: number;
  geometry: { type: "LineString"; coordinates: [number, number][] };
  snapped_waypoints: { latitude: number; longitude: number }[];
  attribution: string;
};

type RouteResponse = {
  route: Route;
  weather:
    | {
        status: "available";
        origin: WeatherObservation;
        destination: WeatherObservation;
      }
    | { status: "unavailable"; error: string };
};

const API_URL =
  process.env.EXPO_PUBLIC_API_URL?.replace(/\/+$/, "") ??
  (Platform.OS === "android"
    ? "http://10.0.2.2:8000"
    : "http://127.0.0.1:8000");

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isPlace(value: unknown): value is Place {
  return (
    isRecord(value) &&
    typeof value.label === "string" &&
    typeof value.latitude === "number" &&
    typeof value.longitude === "number"
  );
}

function isWeatherObservation(value: unknown): value is WeatherObservation {
  return (
    isRecord(value) &&
    typeof value.provider === "string" &&
    (typeof value.time === "string" || value.time === null) &&
    (typeof value.temperature_c === "number" || value.temperature_c === null) &&
    (typeof value.feels_like_c === "number" || value.feels_like_c === null) &&
    (typeof value.precipitation_mm === "number" ||
      value.precipitation_mm === null) &&
    (typeof value.snowfall_cm === "number" || value.snowfall_cm === null) &&
    (typeof value.weather_code === "number" || value.weather_code === null) &&
    (typeof value.wind_kmh === "number" || value.wind_kmh === null) &&
    (typeof value.wind_gusts_kmh === "number" ||
      value.wind_gusts_kmh === null)
  );
}

function isRouteResponse(value: unknown): value is RouteResponse {
  if (!isRecord(value) || !isRecord(value.route) || !isRecord(value.weather)) {
    return false;
  }
  const route = value.route;
  const weather = value.weather;
  const validRoute =
    typeof route.provider === "string" &&
    typeof route.distance_km === "number" &&
    typeof route.duration_minutes === "number" &&
    isRecord(route.geometry) &&
    route.geometry.type === "LineString" &&
    Array.isArray(route.geometry.coordinates) &&
    typeof route.attribution === "string";
  const validWeather =
    (weather.status === "available" &&
      isWeatherObservation(weather.origin) &&
      isWeatherObservation(weather.destination)) ||
    (weather.status === "unavailable" && typeof weather.error === "string");
  return validRoute && validWeather;
}

function weatherDescription(code: number | null): string {
  if (code === null) return "Conditions unavailable";
  if (code === 0) return "Clear";
  if (code <= 3) return "Cloudy";
  if (code === 45 || code === 48) return "Fog";
  if (code >= 71 && code <= 77) return "Snow";
  if (code >= 85 && code <= 86) return "Snow showers";
  if (code >= 51 && code <= 67) return "Rain or drizzle";
  if (code >= 80 && code <= 82) return "Rain showers";
  if (code >= 95) return "Thunderstorms";
  return "Current conditions";
}

function displayNumber(value: number | null, suffix: string): string {
  return value === null ? "—" : `${Math.round(value * 10) / 10}${suffix}`;
}

export default function App() {
  const [originQuery, setOriginQuery] = useState("");
  const [destinationQuery, setDestinationQuery] = useState("");
  const [origin, setOrigin] = useState<Place | null>(null);
  const [destination, setDestination] = useState<Place | null>(null);
  const [originResults, setOriginResults] = useState<Place[]>([]);
  const [destinationResults, setDestinationResults] = useState<Place[]>([]);
  const [searching, setSearching] = useState<"origin" | "destination" | null>(
    null,
  );
  const [locating, setLocating] = useState(false);
  const [routeResponse, setRouteResponse] = useState<RouteResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function searchPlaces(field: "origin" | "destination") {
    const query = field === "origin" ? originQuery : destinationQuery;
    setSearching(field);
    setError("");
    try {
      const response = await fetch(
        `${API_URL}/geocode?query=${encodeURIComponent(query)}`,
      );
      const body: unknown = await response.json();
      if (!response.ok) {
        throw new Error(
          isRecord(body) && typeof body.error === "string"
            ? body.error
            : `Location search failed (${response.status}).`,
        );
      }
      const results =
        isRecord(body) && Array.isArray(body.places)
          ? body.places.filter(isPlace)
          : null;
      if (!results) throw new Error("The location service returned invalid data.");
      if (field === "origin") setOriginResults(results);
      else setDestinationResults(results);
      if (results.length === 0) setError("No matching places found.");
    } catch (searchError) {
      setError(
        searchError instanceof Error
          ? `${searchError.message} Check your API connection at ${API_URL}.`
          : `Could not search for places using ${API_URL}.`,
      );
    } finally {
      setSearching(null);
    }
  }

  async function useCurrentLocation() {
    setLocating(true);
    setError("");
    try {
      const permission = await Location.requestForegroundPermissionsAsync();
      if (permission.status !== "granted") {
        throw new Error("Location permission was not granted.");
      }
      const position = await Location.getCurrentPositionAsync({
        accuracy: Location.Accuracy.Balanced,
      });
      const currentPlace = {
        label: "Current location",
        latitude: position.coords.latitude,
        longitude: position.coords.longitude,
      };
      setOrigin(currentPlace);
      setOriginQuery("Current location");
      setOriginResults([]);
    } catch (locationError) {
      setError(
        locationError instanceof Error
          ? locationError.message
          : "Could not read this device's location.",
      );
    } finally {
      setLocating(false);
    }
  }

  async function planRoute() {
    if (!origin || !destination) {
      setError("Search for and select both a starting point and destination.");
      return;
    }
    setLoading(true);
    setError("");
    setRouteResponse(null);
    try {
      const response = await fetch(`${API_URL}/route`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          origin_lat: origin.latitude,
          origin_lon: origin.longitude,
          dest_lat: destination.latitude,
          dest_lon: destination.longitude,
        }),
      });
      const body: unknown = await response.json();
      if (!response.ok) {
        throw new Error(
          isRecord(body) && typeof body.error === "string"
            ? body.error
            : `Route request failed (${response.status}).`,
        );
      }
      if (!isRouteResponse(body)) {
        throw new Error("The routing service returned an invalid response.");
      }
      setRouteResponse(body);
    } catch (routeError) {
      setError(
        routeError instanceof Error
          ? routeError.message
          : `Could not connect to the route API at ${API_URL}.`,
      );
    } finally {
      setLoading(false);
    }
  }

  async function openNavigation() {
    if (!origin || !destination) return;
    try {
      const originCoordinates = encodeURIComponent(
        `${origin.latitude},${origin.longitude}`,
      );
      const destinationCoordinates = encodeURIComponent(
        `${destination.latitude},${destination.longitude}`,
      );
      await Linking.openURL(
        "https://www.google.com/maps/dir/" +
          `?api=1&origin=${originCoordinates}` +
          `&destination=${destinationCoordinates}&travelmode=driving`,
      );
    } catch (navigationError) {
      setError(
        navigationError instanceof Error
          ? `Could not open navigation: ${navigationError.message}`
          : "Could not open Google Maps directions.",
      );
    }
  }

  return (
    <View style={styles.screen}>
      <StatusBar style="dark" />
      <KeyboardAvoidingView
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        style={styles.flex}
      >
        <ScrollView
          contentContainerStyle={styles.content}
          keyboardShouldPersistTaps="handled"
        >
          <View style={styles.header}>
            <Text style={styles.eyebrow}>WATERLOO → COLLINGWOOD</Text>
            <Text style={styles.title}>Plan your drive.</Text>
            <Text style={styles.subtitle}>
              Real OpenStreetMap road routes, current weather, and navigation in
              Google Maps.
            </Text>
          </View>

          <View style={styles.card}>
            <Text style={styles.sectionTitle}>STARTING POINT</Text>
            <LocationSearch
              query={originQuery}
              place={origin}
              results={originResults}
              searching={searching === "origin"}
              onChangeQuery={(query) => {
                setOriginQuery(query);
                setOrigin(null);
                setOriginResults([]);
                setRouteResponse(null);
              }}
              onSearch={() => searchPlaces("origin")}
              onSelect={(place) => {
                setOrigin(place);
                setOriginQuery(place.label);
                setOriginResults([]);
                setRouteResponse(null);
              }}
            />
            <Pressable
              accessibilityRole="button"
              disabled={locating}
              onPress={useCurrentLocation}
              style={styles.locationButton}
            >
              {locating ? (
                <ActivityIndicator color="#28735b" size="small" />
              ) : (
                <Text style={styles.locationButtonText}>
                  Use this device's current location
                </Text>
              )}
            </Pressable>

            <Text style={[styles.sectionTitle, styles.destinationHeading]}>
              DESTINATION
            </Text>
            <LocationSearch
              query={destinationQuery}
              place={destination}
              results={destinationResults}
              searching={searching === "destination"}
              onChangeQuery={(query) => {
                setDestinationQuery(query);
                setDestination(null);
                setDestinationResults([]);
                setRouteResponse(null);
              }}
              onSearch={() => searchPlaces("destination")}
              onSelect={(place) => {
                setDestination(place);
                setDestinationQuery(place.label);
                setDestinationResults([]);
                setRouteResponse(null);
              }}
            />
          </View>

          <Pressable
            accessibilityRole="button"
            disabled={loading}
            onPress={planRoute}
            style={({ pressed }) => [
              styles.submitButton,
              pressed && styles.submitButtonPressed,
              loading && styles.submitButtonDisabled,
            ]}
          >
            {loading ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={styles.submitText}>Plan road route</Text>
            )}
          </Pressable>

          {error ? (
            <View accessibilityRole="alert" style={styles.errorBox}>
              <Text style={styles.errorText}>{error}</Text>
            </View>
          ) : null}

          {routeResponse ? (
            <RouteCard
              route={routeResponse.route}
              weather={routeResponse.weather}
              onNavigate={openNavigation}
            />
          ) : null}

          <Text style={styles.disclaimer}>
            Trip planning only—not a safety-rated route or turn-by-turn
            navigation system. Check Ontario 511, official weather alerts, road
            signs, and conditions before and during travel. Google Maps may
            calculate a different route.
          </Text>
        </ScrollView>
      </KeyboardAvoidingView>
    </View>
  );
}

function LocationSearch({
  query,
  place,
  results,
  searching,
  onChangeQuery,
  onSearch,
  onSelect,
}: {
  query: string;
  place: Place | null;
  results: Place[];
  searching: boolean;
  onChangeQuery: (query: string) => void;
  onSearch: () => void;
  onSelect: (place: Place) => void;
}) {
  return (
    <View>
      <View style={styles.searchRow}>
        <TextInput
          accessibilityLabel="Search for a place"
          autoCapitalize="words"
          onChangeText={onChangeQuery}
          onSubmitEditing={onSearch}
          placeholder="City, address, or place"
          placeholderTextColor="#93a19b"
          returnKeyType="search"
          style={styles.searchInput}
          value={query}
        />
        <Pressable
          accessibilityRole="button"
          disabled={searching}
          onPress={onSearch}
          style={styles.searchButton}
        >
          {searching ? (
            <ActivityIndicator color="#fff" size="small" />
          ) : (
            <Text style={styles.searchButtonText}>Search</Text>
          )}
        </Pressable>
      </View>
      {place ? (
        <Text style={styles.selectedPlace}>
          Selected: {place.label}
        </Text>
      ) : null}
      {results.map((result) => (
        <Pressable
          accessibilityRole="button"
          key={`${result.label}:${result.latitude}:${result.longitude}`}
          onPress={() => onSelect(result)}
          style={styles.searchResult}
        >
          <Text style={styles.searchResultText}>{result.label}</Text>
        </Pressable>
      ))}
    </View>
  );
}

function RouteCard({
  route,
  weather,
  onNavigate,
}: {
  route: Route;
  weather: RouteResponse["weather"];
  onNavigate: () => void;
}) {
  return (
    <View style={styles.resultCard}>
      <Text style={styles.resultEyebrow}>ROAD ROUTE</Text>
      <View style={styles.resultTop}>
        <Text style={styles.resultTitle}>
          {Math.round(route.duration_minutes)} min
        </Text>
        <View style={styles.distancePill}>
          <Text style={styles.distanceText}>{route.distance_km} km</Text>
        </View>
      </View>
      <Text style={styles.resultCaption}>Estimated by the road-routing service</Text>

      <Pressable
        accessibilityRole="button"
        onPress={onNavigate}
        style={styles.navigationButton}
      >
        <Text style={styles.navigationButtonText}>
          Open driving directions in Google Maps
        </Text>
      </Pressable>

      <View style={styles.divider} />
      <Text style={styles.routeLabel}>CURRENT WEATHER · OPEN-METEO</Text>
      {weather.status === "available" ? (
        <>
          <WeatherSummary label="At start" weather={weather.origin} />
          <WeatherSummary label="At destination" weather={weather.destination} />
        </>
      ) : (
        <Text style={styles.weatherUnavailable}>
          Live weather is unavailable: {weather.error}
        </Text>
      )}
      <Text style={styles.attribution}>{route.attribution}</Text>
    </View>
  );
}

function WeatherSummary({
  label,
  weather,
}: {
  label: string;
  weather: WeatherObservation;
}) {
  return (
    <View style={styles.weatherSummary}>
      <View style={styles.weatherHeading}>
        <Text style={styles.weatherPlace}>{label}</Text>
        <Text style={styles.weatherTime}>{weather.time ?? "Time unavailable"}</Text>
      </View>
      <Text style={styles.weatherCondition}>
        {displayNumber(weather.temperature_c, "°C")} ·{" "}
        {weatherDescription(weather.weather_code)}
      </Text>
      <Text style={styles.weatherDetails}>
        Snow {displayNumber(weather.snowfall_cm, " cm")} · Wind{" "}
        {displayNumber(weather.wind_kmh, " km/h")} · Gusts{" "}
        {displayNumber(weather.wind_gusts_kmh, " km/h")}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  screen: { backgroundColor: "#f3f6f4", flex: 1 },
  content: {
    alignSelf: "center",
    maxWidth: 620,
    paddingBottom: 36,
    paddingHorizontal: 20,
    paddingTop: Platform.OS === "web" ? 36 : 22,
    width: "100%",
  },
  header: { marginBottom: 24, paddingHorizontal: 4, paddingTop: 12 },
  eyebrow: {
    color: "#35826d",
    fontSize: 11,
    fontWeight: "800",
    letterSpacing: 1.7,
    marginBottom: 12,
  },
  title: {
    color: "#152d29",
    fontSize: 38,
    fontWeight: "800",
    letterSpacing: -1.3,
    lineHeight: 42,
  },
  subtitle: { color: "#657771", fontSize: 15, lineHeight: 22, marginTop: 10 },
  card: {
    backgroundColor: "#fff",
    borderColor: "#e6ece8",
    borderRadius: 18,
    borderWidth: 1,
    marginBottom: 14,
    padding: 18,
  },
  sectionTitle: {
    color: "#29473f",
    fontSize: 12,
    fontWeight: "800",
    letterSpacing: 1.1,
    marginBottom: 12,
  },
  destinationHeading: { marginTop: 22 },
  searchRow: { flexDirection: "row", gap: 8 },
  searchInput: {
    backgroundColor: "#f7f9f8",
    borderColor: "#e5ece8",
    borderRadius: 10,
    borderWidth: 1,
    color: "#203b34",
    flex: 1,
    fontSize: 14,
    minHeight: 46,
    paddingHorizontal: 12,
  },
  searchButton: {
    alignItems: "center",
    backgroundColor: "#43836f",
    borderRadius: 10,
    justifyContent: "center",
    minWidth: 76,
    paddingHorizontal: 14,
  },
  searchButtonText: { color: "#fff", fontSize: 13, fontWeight: "800" },
  selectedPlace: { color: "#28735b", fontSize: 12, marginTop: 9 },
  searchResult: {
    borderBottomColor: "#edf1ef",
    borderBottomWidth: 1,
    paddingVertical: 12,
  },
  searchResultText: { color: "#334b43", fontSize: 13, lineHeight: 18 },
  locationButton: {
    alignSelf: "flex-start",
    marginTop: 12,
    minHeight: 32,
    justifyContent: "center",
  },
  locationButtonText: { color: "#28735b", fontSize: 12, fontWeight: "700" },
  submitButton: {
    alignItems: "center",
    backgroundColor: "#24745b",
    borderRadius: 14,
    justifyContent: "center",
    marginBottom: 14,
    minHeight: 54,
  },
  submitButtonPressed: { backgroundColor: "#1c614b" },
  submitButtonDisabled: { opacity: 0.75 },
  submitText: { color: "#fff", fontSize: 16, fontWeight: "800" },
  errorBox: {
    backgroundColor: "#fff0ed",
    borderColor: "#f2c9c1",
    borderRadius: 12,
    borderWidth: 1,
    marginBottom: 14,
    padding: 14,
  },
  errorText: { color: "#9e3b2c", fontSize: 13, lineHeight: 19 },
  resultCard: {
    backgroundColor: "#fff",
    borderColor: "#dbe9e2",
    borderRadius: 18,
    borderWidth: 1,
    marginBottom: 18,
    padding: 18,
  },
  resultTop: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
  },
  resultEyebrow: {
    color: "#43836f",
    fontSize: 10,
    fontWeight: "800",
    letterSpacing: 1,
  },
  resultTitle: { color: "#183b31", fontSize: 32, fontWeight: "800", marginTop: 4 },
  distancePill: {
    backgroundColor: "#e8f3ee",
    borderRadius: 20,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  distanceText: { color: "#28634f", fontSize: 12, fontWeight: "800" },
  resultCaption: { color: "#74857e", fontSize: 12, marginTop: 2 },
  navigationButton: {
    alignItems: "center",
    backgroundColor: "#e8f3ee",
    borderRadius: 11,
    justifyContent: "center",
    marginTop: 16,
    minHeight: 48,
    paddingHorizontal: 12,
  },
  navigationButtonText: {
    color: "#28634f",
    fontSize: 13,
    fontWeight: "800",
    textAlign: "center",
  },
  divider: { backgroundColor: "#edf1ef", height: 1, marginVertical: 16 },
  routeLabel: {
    color: "#7a8c85",
    fontSize: 10,
    fontWeight: "800",
    letterSpacing: 1,
    marginBottom: 8,
  },
  weatherSummary: {
    borderBottomColor: "#edf1ef",
    borderBottomWidth: 1,
    paddingVertical: 11,
  },
  weatherHeading: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
  },
  weatherPlace: { color: "#315849", fontSize: 12, fontWeight: "800" },
  weatherTime: { color: "#8b9892", fontSize: 10 },
  weatherCondition: { color: "#334b43", fontSize: 14, fontWeight: "700", marginTop: 6 },
  weatherDetails: { color: "#74857e", fontSize: 11, marginTop: 4 },
  weatherUnavailable: { color: "#9e3b2c", fontSize: 12, lineHeight: 18 },
  attribution: { color: "#87968f", fontSize: 10, marginTop: 14 },
  disclaimer: {
    color: "#87968f",
    fontSize: 11,
    lineHeight: 17,
    paddingHorizontal: 8,
    textAlign: "center",
  },
});
