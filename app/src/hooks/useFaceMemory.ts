/**
 * useFaceMemory -- face reference storage for Elora's people memory
 *
 * When the user says "this is Maya" while the camera is active:
 *   1. Resize the captured frame for efficient upload
 *   2. POST the image to /face/reference on the backend
 *   3. Backend uses Gemini Vision to find and crop the face, stores in GCS
 *   4. Associate the crop with the person record in people memory
 *
 * Note: We skip client-side face detection (expo-face-detector is deprecated)
 * and let the backend handle face finding via Gemini Vision. This is more
 * accurate and works in Expo Go without native modules.
 */

import { useCallback } from "react";
import * as ImageManipulator from "expo-image-manipulator";
import * as FileSystem from "expo-file-system/legacy";
import { BACKEND_URL } from "../config";

export interface FaceReferenceResult {
  status: "ok" | "no_face" | "error";
  personId?: string;
  referenceUrl?: string;
  error?: string;
}

export interface UseFaceMemoryReturn {
  /** Upload an image as the face reference for a person. Backend handles face detection. */
  storeFaceReference: (
    imageUri: string,
    personName: string,
    userId: string,
    authToken?: string
  ) => Promise<FaceReferenceResult>;
  /** Upload a base64 JPEG as the face reference for a person. */
  storeFaceReferenceFromBase64: (
    base64Jpeg: string,
    personName: string,
    userId: string,
    authToken?: string
  ) => Promise<FaceReferenceResult>;
}

export function useFaceMemory(): UseFaceMemoryReturn {
  const storeFaceReference = useCallback(
    async (
      imageUri: string,
      personName: string,
      userId: string,
      authToken?: string
    ): Promise<FaceReferenceResult> => {
      try {
        // Resize for efficient upload (256px wide is enough for face reference)
        const resized = await ImageManipulator.manipulateAsync(
          imageUri,
          [{ resize: { width: 256 } }],
          { compress: 0.85, format: ImageManipulator.SaveFormat.JPEG }
        );

        const imageBase64 = await FileSystem.readAsStringAsync(resized.uri, {
          encoding: FileSystem.EncodingType.Base64,
        });
        await FileSystem.deleteAsync(resized.uri, { idempotent: true });

        // Upload to backend -- backend handles face detection and cropping
        const response = await fetch(`${BACKEND_URL}/face/reference`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            user_id: userId,
            person_name: personName,
            face_image_base64: imageBase64,
            token: authToken ?? "",
          }),
        });

        if (!response.ok) {
          return { status: "error", error: `Upload failed: ${response.status}` };
        }

        const data = await response.json();
        return {
          status: "ok",
          personId: data.person_id,
          referenceUrl: data.reference_url,
        };
      } catch (e: any) {
        console.error("[useFaceMemory] storeFaceReference error:", e);
        return { status: "error", error: String(e?.message ?? e) };
      }
    },
    []
  );

  const storeFaceReferenceFromBase64 = useCallback(
    async (
      base64Jpeg: string,
      personName: string,
      userId: string,
      authToken?: string
    ): Promise<FaceReferenceResult> => {
      try {
        // Write base64 to a temp file so ImageManipulator can process it
        const tempUri = `${FileSystem.cacheDirectory}face_ref_tmp_${Date.now()}.jpg`;
        await FileSystem.writeAsStringAsync(tempUri, base64Jpeg, {
          encoding: FileSystem.EncodingType.Base64,
        });

        const result = await storeFaceReference(
          tempUri,
          personName,
          userId,
          authToken
        );

        // Clean up temp file
        await FileSystem.deleteAsync(tempUri, { idempotent: true });

        return result;
      } catch (e: any) {
        return { status: "error", error: String(e?.message ?? e) };
      }
    },
    [storeFaceReference]
  );

  return { storeFaceReference, storeFaceReferenceFromBase64 };
}
