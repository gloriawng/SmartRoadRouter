import { StatusBar } from "expo-status-bar";
import { useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

type Coordinates = {
  name: string;
  latitude: number;
  longitude: number;
};

type RouteResult = {
  origin: string;
  destination: string;
  nodes: Coordinates[];
  distance_km: number;
  estimated_travel_time_seconds: number;
  average_road_risk: number;
  weather_severity: number;
  objective_cost_seconds: number;
};

type Place = {
  label: string;
  latitude: string;
  longitude: string;
};

function isRouteResult(value: unknown): value is RouteResult {
  if (typeof value !== "object" || value === null) return false;
  const result = value as Record<string, unknown>;
  return (
    typeof result.origin === "string" &&
    typeof result.destination === "string" &&
    Array.isArray(result.nodes) &&
    typeof result.distance_km === "number" &&
    typeof result.estimated_travel_time_seconds === "number" &&
    typeof result.average_road_risk === "number" &&
    typeof result.weather_severity === "number" &&
    typeof result.objective_cost_seconds === "number"
  );
}

const PLACES: Place[] = [
  { label: "Uptown Waterloo", latitude: "43.4643", longitude: "-80.5204" },
  { label: "Waterloo East", latitude: "43.4490", longitude: "-80.4750" },
];

const API_URL =
  process.env.EXPO_PUBLIC_API_URL?.replace(/\/+$/, "") ??
  (Platform.OS === "android"
    ? "http://10.0.2.2:8000"
    : "http://127.0.0.1:8000");

function NumberField({
  label,
  value,
  onChangeText,
  suffix,
}: {
  label: string;
  value: string;
  onChangeText: (value: string) => void;
  suffix: string;
}) {
  return (
    <View style={styles.field}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <View style={styles.inputWrap}>
        <TextInput
          accessibilityLabel={label}
          keyboardType="decimal-pad"
          onChangeText={onChangeText}
          style={styles.input}
          value={value}
        />
        <Text style={styles.suffix}>{suffix}</Text>
      </View>
    </View>
  );
}

export default function App() {
  const [origin, setOrigin] = useState(PLACES[0]);
  const [destination, setDestination] = useState(PLACES[1]);
  const [snowfall, setSnowfall] = useState("0");
  const [wind, setWind] = useState("10");
  const [temperature, setTemperature] = useState("2");
  const [safetyWeight, setSafetyWeight] = useState(0.7);
  const [route, setRoute] = useState<RouteResult | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function planRoute() {
    setLoading(true);
    setError("");
    setRoute(null);

    try {
      const response = await fetch(`${API_URL}/route`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          origin_lat: Number(origin.latitude),
          origin_lon: Number(origin.longitude),
          dest_lat: Number(destination.latitude),
          dest_lon: Number(destination.longitude),
          safety_weight: safetyWeight,
          weather: {
            snowfall_cm_per_hour: Number(snowfall),
            wind_kmh: Number(wind),
            temperature_c: Number(temperature),
          },
        }),
      });
      const body: unknown = await response.json();
      if (!response.ok) {
        const message =
          typeof body === "object" &&
          body !== null &&
          "error" in body &&
          typeof body.error === "string"
            ? body.error
            : `Request failed (${response.status}).`;
        throw new Error(message);
      }
      if (!isRouteResult(body)) {
        throw new Error("The API returned an invalid route response.");
      }
      setRoute(body);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? `${requestError.message} Check that the API is running at ${API_URL}.`
          : `Could not connect to the API at ${API_URL}.`,
      );
    } finally {
      setLoading(false);
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
            <Text style={styles.eyebrow}>WATERLOO · WINTER ROUTING</Text>
            <Text style={styles.title}>A safer way{`\n`}to get there.</Text>
            <Text style={styles.subtitle}>
              Compare your route with weather-aware road risk.
            </Text>
          </View>

          <View style={styles.card}>
            <Text style={styles.sectionTitle}>YOUR TRIP</Text>
            <Text style={styles.fieldLabel}>FROM</Text>
            <View style={styles.placeRow}>
              {PLACES.map((place) => (
                <PlaceButton
                  key={place.label}
                  place={place}
                  selected={origin.label === place.label}
                  onPress={() => {
                    setOrigin(place);
                    if (destination.label === place.label) {
                      setDestination(
                        PLACES.find((candidate) => candidate.label !== place.label)!,
                      );
                    }
                  }}
                />
              ))}
            </View>
            <Text style={[styles.fieldLabel, styles.destinationLabel]}>TO</Text>
            <View style={styles.placeRow}>
              {PLACES.map((place) => (
                <PlaceButton
                  key={place.label}
                  place={place}
                  selected={destination.label === place.label}
                  onPress={() => {
                    setDestination(place);
                    if (origin.label === place.label) {
                      setOrigin(
                        PLACES.find((candidate) => candidate.label !== place.label)!,
                      );
                    }
                  }}
                />
              ))}
            </View>
          </View>

          <View style={styles.card}>
            <Text style={styles.sectionTitle}>CURRENT CONDITIONS</Text>
            <View style={styles.weatherRow}>
              <NumberField
                label="Snowfall"
                suffix="cm/h"
                value={snowfall}
                onChangeText={setSnowfall}
              />
              <NumberField
                label="Wind"
                suffix="km/h"
                value={wind}
                onChangeText={setWind}
              />
              <NumberField
                label="Temperature"
                suffix="°C"
                value={temperature}
                onChangeText={setTemperature}
              />
            </View>
            <Text style={[styles.fieldLabel, styles.weightLabel]}>
              ROUTING PRIORITY
            </Text>
            <View style={styles.priorityRow}>
              {[
                { value: 0, label: "QUICKER" },
                { value: 0.5, label: "BALANCED" },
                { value: 1, label: "SAFER" },
              ].map((option) => (
                <Pressable
                  accessibilityRole="button"
                  accessibilityState={{ selected: safetyWeight === option.value }}
                  key={option.value}
                  onPress={() => setSafetyWeight(option.value)}
                  style={[
                    styles.priorityButton,
                    safetyWeight === option.value && styles.priorityButtonActive,
                  ]}
                >
                  <Text
                    style={[
                      styles.priorityText,
                      safetyWeight === option.value && styles.priorityTextActive,
                    ]}
                  >
                    {option.label}
                  </Text>
                </Pressable>
              ))}
            </View>
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
              <Text style={styles.submitText}>Find my route</Text>
            )}
          </Pressable>

          {error ? (
            <View accessibilityRole="alert" style={styles.errorBox}>
              <Text style={styles.errorText}>{error}</Text>
            </View>
          ) : null}

          {route ? <RouteCard route={route} /> : null}

          <Text style={styles.disclaimer}>
            Demo only · Uses a small synthetic Waterloo road network and
            manually entered weather. Not for real travel or safety decisions.
          </Text>
        </ScrollView>
      </KeyboardAvoidingView>
    </View>
  );
}

function PlaceButton({
  place,
  selected,
  onPress,
}: {
  place: Place;
  selected: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected }}
      onPress={onPress}
      style={[styles.placeButton, selected && styles.placeButtonSelected]}
    >
      <Text style={[styles.placeText, selected && styles.placeTextSelected]}>
        {place.label}
      </Text>
    </Pressable>
  );
}

function RouteCard({ route }: { route: RouteResult }) {
  const minutes = Math.round(route.estimated_travel_time_seconds / 60);
  return (
    <View style={styles.resultCard}>
      <View style={styles.resultTop}>
        <View>
          <Text style={styles.resultEyebrow}>RECOMMENDED ROUTE</Text>
          <Text style={styles.resultTitle}>{minutes} min</Text>
        </View>
        <View style={styles.distancePill}>
          <Text style={styles.distanceText}>{route.distance_km} km</Text>
        </View>
      </View>
      <Text style={styles.resultCaption}>
        {route.origin} to {route.destination}
      </Text>
      <View style={styles.divider} />
      <Text style={styles.routeLabel}>ROUTE STOPS</Text>
      {route.nodes.map((node, index) => (
        <View key={`${node.name}-${index}`} style={styles.stopRow}>
          <View style={styles.stopMarker}>
            <Text style={styles.stopNumber}>{index + 1}</Text>
          </View>
          <Text style={styles.stopName}>{node.name}</Text>
        </View>
      ))}
      <View style={styles.metricsRow}>
        <Metric label="ROAD RISK" value={route.average_road_risk.toFixed(2)} />
        <Metric label="WEATHER" value={route.weather_severity.toFixed(2)} />
        <Metric
          label="COST"
          value={`${Math.round(route.objective_cost_seconds / 60)} min`}
        />
      </View>
    </View>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.metric}>
      <Text style={styles.metricLabel}>{label}</Text>
      <Text style={styles.metricValue}>{value}</Text>
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
    marginBottom: 18,
  },
  fieldLabel: {
    color: "#7a8c85",
    fontSize: 10,
    fontWeight: "800",
    letterSpacing: 1,
    marginBottom: 8,
  },
  placeRow: { flexDirection: "row", gap: 8 },
  placeButton: {
    alignItems: "center",
    backgroundColor: "#f5f8f6",
    borderColor: "#e5ece8",
    borderRadius: 11,
    borderWidth: 1,
    flex: 1,
    justifyContent: "center",
    minHeight: 46,
    paddingHorizontal: 8,
  },
  placeButtonSelected: { backgroundColor: "#e7f3ee", borderColor: "#6aa58f" },
  placeText: { color: "#61746c", fontSize: 12, fontWeight: "600" },
  placeTextSelected: { color: "#22644f", fontWeight: "800" },
  destinationLabel: { marginTop: 18 },
  weatherRow: { flexDirection: "row", gap: 8 },
  field: { flex: 1, minWidth: 0 },
  inputWrap: {
    alignItems: "center",
    backgroundColor: "#f7f9f8",
    borderColor: "#e5ece8",
    borderRadius: 10,
    borderWidth: 1,
    flexDirection: "row",
    minHeight: 44,
    paddingHorizontal: 9,
  },
  input: {
    color: "#203b34",
    flex: 1,
    fontSize: 15,
    fontWeight: "700",
    minWidth: 0,
    paddingVertical: 8,
  },
  suffix: { color: "#84948d", fontSize: 10, fontWeight: "600" },
  weightLabel: { marginTop: 20 },
  priorityRow: {
    backgroundColor: "#f3f6f4",
    borderRadius: 11,
    flexDirection: "row",
    padding: 4,
  },
  priorityButton: {
    alignItems: "center",
    borderRadius: 8,
    flex: 1,
    justifyContent: "center",
    minHeight: 38,
    paddingHorizontal: 4,
  },
  priorityButtonActive: {
    backgroundColor: "#fff",
    elevation: 1,
    shadowColor: "#18382e",
    shadowOpacity: 0.08,
    shadowRadius: 4,
  },
  priorityText: { color: "#7b8b85", fontSize: 10, fontWeight: "800" },
  priorityTextActive: { color: "#28735b" },
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
  resultTop: { alignItems: "center", flexDirection: "row", justifyContent: "space-between" },
  resultEyebrow: {
    color: "#43836f",
    fontSize: 10,
    fontWeight: "800",
    letterSpacing: 1,
  },
  resultTitle: { color: "#183b31", fontSize: 32, fontWeight: "800", marginTop: 3 },
  distancePill: {
    backgroundColor: "#e8f3ee",
    borderRadius: 20,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  distanceText: { color: "#28634f", fontSize: 12, fontWeight: "800" },
  resultCaption: { color: "#74857e", fontSize: 13, marginTop: 2 },
  divider: { backgroundColor: "#edf1ef", height: 1, marginVertical: 16 },
  routeLabel: {
    color: "#7a8c85",
    fontSize: 10,
    fontWeight: "800",
    letterSpacing: 1,
    marginBottom: 12,
  },
  stopRow: { alignItems: "center", flexDirection: "row", marginBottom: 10 },
  stopMarker: {
    alignItems: "center",
    backgroundColor: "#e9f3ee",
    borderRadius: 11,
    height: 22,
    justifyContent: "center",
    marginRight: 10,
    width: 22,
  },
  stopNumber: { color: "#36765f", fontSize: 10, fontWeight: "800" },
  stopName: { color: "#334b43", fontSize: 13, fontWeight: "600" },
  metricsRow: {
    borderTopColor: "#edf1ef",
    borderTopWidth: 1,
    flexDirection: "row",
    justifyContent: "space-between",
    marginTop: 8,
    paddingTop: 14,
  },
  metric: { flex: 1 },
  metricLabel: { color: "#87968f", fontSize: 9, fontWeight: "800", letterSpacing: 0.7 },
  metricValue: { color: "#315849", fontSize: 15, fontWeight: "800", marginTop: 5 },
  disclaimer: {
    color: "#87968f",
    fontSize: 11,
    lineHeight: 17,
    paddingHorizontal: 8,
    textAlign: "center",
  },
});
