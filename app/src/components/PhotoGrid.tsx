/**
 * PhotoGrid -- displays a grid of photos returned by a face search
 * Shown inline in the chat when Elora finds photos of a person
 */

import React, { useState, useMemo } from "react";
import {
  View,
  Image,
  TouchableOpacity,
  StyleSheet,
  Modal,
  Dimensions,
  Text,
  FlatList,
  ScrollView,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useTheme, borderRadius } from "../theme";

const { width } = Dimensions.get("window");
const GRID_ITEM_SIZE = (width - 64 - 8) / 3; // 3 cols, 16px padding each side, 4px gap

interface PhotoGridProps {
  uris: string[];
  /** Optional label (e.g. "3 photos of Maya") */
  label?: string;
}

export function PhotoGrid({ uris, label }: PhotoGridProps) {
  const { colors } = useTheme();
  const [lightboxUri, setLightboxUri] = useState<string | null>(null);
  const [lightboxIndex, setLightboxIndex] = useState(0);

  if (!uris || uris.length === 0) return null;

  const openLightbox = (uri: string, index: number) => {
    setLightboxUri(uri);
    setLightboxIndex(index);
  };

  const closeLightbox = () => setLightboxUri(null);

  const goNext = () => {
    const next = (lightboxIndex + 1) % uris.length;
    setLightboxIndex(next);
    setLightboxUri(uris[next]);
  };

  const goPrev = () => {
    const prev = (lightboxIndex - 1 + uris.length) % uris.length;
    setLightboxIndex(prev);
    setLightboxUri(uris[prev]);
  };

  return (
    <View style={styles.container}>
      {label && <Text style={[styles.label, { color: colors.textSecondary }]}>{label}</Text>}

      {/* Photo grid — max 9 shown, +N overflow badge */}
      <View style={styles.grid}>
        {uris.slice(0, 9).map((uri, i) => {
          const isOverflow = i === 8 && uris.length > 9;
          return (
            <TouchableOpacity
              key={uri + i}
              onPress={() => openLightbox(uri, i)}
              style={[styles.cell, { backgroundColor: colors.surface }]}
              activeOpacity={0.85}
            >
              <Image source={{ uri }} style={styles.thumb} resizeMode="cover" />
              {isOverflow && (
                <View style={styles.overflowBadge}>
                  <Text style={styles.overflowText}>+{uris.length - 8}</Text>
                </View>
              )}
            </TouchableOpacity>
          );
        })}
      </View>

      {/* Lightbox */}
      <Modal
        visible={lightboxUri !== null}
        transparent
        animationType="fade"
        onRequestClose={closeLightbox}
      >
        <View style={styles.lightboxBg}>
          <TouchableOpacity style={styles.lightboxClose} onPress={closeLightbox}>
            <Ionicons name="close" size={28} color="#fff" />
          </TouchableOpacity>

          {lightboxUri && (
            <Image
              source={{ uri: lightboxUri }}
              style={styles.lightboxImage}
              resizeMode="contain"
            />
          )}

          {uris.length > 1 && (
            <View style={styles.lightboxNav}>
              <TouchableOpacity onPress={goPrev} style={styles.navBtn}>
                <Ionicons name="chevron-back" size={32} color="#fff" />
              </TouchableOpacity>
              <Text style={styles.lightboxCounter}>
                {lightboxIndex + 1} / {uris.length}
              </Text>
              <TouchableOpacity onPress={goNext} style={styles.navBtn}>
                <Ionicons name="chevron-forward" size={32} color="#fff" />
              </TouchableOpacity>
            </View>
          )}
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    marginTop: 8,
  },
  label: {
    fontSize: 12,
    marginBottom: 6,
    fontStyle: "italic",
  },
  grid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 4,
  },
  cell: {
    width: GRID_ITEM_SIZE,
    height: GRID_ITEM_SIZE,
    borderRadius: borderRadius.sm,
    overflow: "hidden",
  },
  thumb: {
    width: "100%",
    height: "100%",
  },
  overflowBadge: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "rgba(0,0,0,0.55)",
    alignItems: "center",
    justifyContent: "center",
  },
  overflowText: {
    color: "#fff",
    fontSize: 18,
    fontWeight: "700",
  },
  // Lightbox -- intentionally dark overlay for photo viewing
  lightboxBg: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.95)",
    alignItems: "center",
    justifyContent: "center",
  },
  lightboxClose: {
    position: "absolute",
    top: 52,
    right: 20,
    zIndex: 10,
    padding: 8,
  },
  lightboxImage: {
    width: width,
    height: width * 1.2,
  },
  lightboxNav: {
    position: "absolute",
    bottom: 60,
    flexDirection: "row",
    alignItems: "center",
    gap: 32,
  },
  navBtn: {
    padding: 12,
  },
  lightboxCounter: {
    color: "#fff",
    fontSize: 16,
    fontWeight: "600",
  },
});
