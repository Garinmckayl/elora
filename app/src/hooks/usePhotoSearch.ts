/**
 * usePhotoSearch -- find photos containing a specific person using Gemini Vision
 *
 * Pipeline:
 *   1. Get recent photos from camera roll (expo-media-library)
 *   2. Resize each photo to a smaller size for efficient upload
 *   3. Send resized photo + the person's reference to the backend
 *   4. Backend uses Gemini Vision to compare: "Is this the same person?"
 *   5. Return matching photo URIs
 *
 * Note: We skip client-side face detection entirely (expo-face-detector is
 * deprecated) and let Gemini Vision handle both face finding and comparison
 * in one pass. This is more accurate and works in Expo Go without native modules.
 */

import { useState, useCallback, useRef } from "react";
import * as MediaLibrary from "expo-media-library";
import * as ImageManipulator from "expo-image-manipulator";
import * as FileSystem from "expo-file-system/legacy";
import { BACKEND_URL } from "../config";

export interface PhotoSearchResult {
  uri: string;
  filename: string;
  creationTime: number;
  confidence: "high" | "medium" | "low";
}

export interface PhotoSearchProgress {
  scanned: number;
  total: number;
  found: number;
  status: "idle" | "scanning" | "done" | "error";
}

export interface UsePhotoSearchReturn {
  progress: PhotoSearchProgress;
  /** Find all photos in the camera roll that contain a given person. */
  findPhotosWithPerson: (
    personName: string,
    userId: string,
    authToken?: string,
    options?: { limit?: number; onProgress?: (p: PhotoSearchProgress) => void }
  ) => Promise<PhotoSearchResult[]>;
  /** Cancel an in-progress search. */
  cancelSearch: () => void;
}

export function usePhotoSearch(): UsePhotoSearchReturn {
  const [progress, setProgress] = useState<PhotoSearchProgress>({
    scanned: 0,
    total: 0,
    found: 0,
    status: "idle",
  });

  const cancelRef = useRef(false);

  const cancelSearch = useCallback(() => {
    cancelRef.current = true;
  }, []);

  const findPhotosWithPerson = useCallback(
    async (
      personName: string,
      userId: string,
      authToken?: string,
      options: { limit?: number; onProgress?: (p: PhotoSearchProgress) => void } = {}
    ): Promise<PhotoSearchResult[]> => {
      const { limit = 200, onProgress } = options;
      cancelRef.current = false;

      const updateProgress = (p: Partial<PhotoSearchProgress>) => {
        setProgress((prev) => {
          const next = { ...prev, ...p };
          onProgress?.(next);
          return next;
        });
      };

      // 1. Get permission
      const { status } = await MediaLibrary.requestPermissionsAsync();
      if (status !== "granted") {
        updateProgress({ status: "error" });
        return [];
      }

      // 2. Fetch reference crop from backend
      let referenceBase64: string | null = null;
      try {
        const refResp = await fetch(
          `${BACKEND_URL}/face/reference?user_id=${encodeURIComponent(userId)}&person_name=${encodeURIComponent(personName)}&token=${encodeURIComponent(authToken ?? "")}`
        );
        if (refResp.ok) {
          const refData = await refResp.json();
          referenceBase64 = refData.face_image_base64 ?? null;
        }
      } catch {
        // No reference stored — fall back to Gemini text description comparison
      }

      // 3. Get photos from camera roll
      const mediaResult = await MediaLibrary.getAssetsAsync({
        first: limit,
        mediaType: ["photo"],
        sortBy: [MediaLibrary.SortBy.creationTime],
      });

      const assets = mediaResult.assets;
      updateProgress({ total: assets.length, status: "scanning", scanned: 0, found: 0 });

      const results: PhotoSearchResult[] = [];

      // 4. Process each photo -- resize and send to backend for Gemini Vision comparison
      for (let i = 0; i < assets.length; i++) {
        if (cancelRef.current) break;

        const asset = assets[i];

        try {
          // Resize the photo to reduce upload size (320px wide is enough for face matching)
          const resized = await ImageManipulator.manipulateAsync(
            asset.uri,
            [{ resize: { width: 320 } }],
            { compress: 0.6, format: ImageManipulator.SaveFormat.JPEG }
          );

          const photoBase64 = await FileSystem.readAsStringAsync(resized.uri, {
            encoding: FileSystem.EncodingType.Base64,
          });
          await FileSystem.deleteAsync(resized.uri, { idempotent: true });

          // Compare via backend (Gemini Vision handles face detection + comparison)
          const compareResp = await fetch(`${BACKEND_URL}/face/compare`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              user_id: userId,
              person_name: personName,
              face_image_base64: photoBase64,
              reference_base64: referenceBase64,
              token: authToken ?? "",
            }),
          });

          if (!compareResp.ok) {
            updateProgress({ scanned: i + 1 });
            continue;
          }

          const cmp = await compareResp.json();

          if (cmp.match === true) {
            results.push({
              uri: asset.uri,
              filename: asset.filename,
              creationTime: asset.creationTime,
              confidence:
                cmp.confidence === "high"
                  ? "high"
                  : cmp.confidence === "medium"
                  ? "medium"
                  : "low",
            });
            updateProgress({ scanned: i + 1, found: results.length });
          } else {
            updateProgress({ scanned: i + 1 });
          }
        } catch {
          // Skip photos that fail (permissions, corrupted, etc.)
          updateProgress({ scanned: i + 1 });
        }
      }

      updateProgress({ status: "done" });
      return results;
    },
    []
  );

  return { progress, findPhotosWithPerson, cancelSearch };
}
