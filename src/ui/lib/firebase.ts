/**
 * Firebase client-side SDK initialization and auth helpers for CareBridge.
 *
 * Guards: if any NEXT_PUBLIC_FIREBASE_* env var is missing, all functions
 * return null / log a warning and do NOT throw.  This lets the app boot
 * even when Firebase is not configured (the Google button is hidden).
 */

import { initializeApp, type FirebaseApp } from "firebase/app";
import {
  type Auth,
  type User,
  getAuth,
  GoogleAuthProvider,
  signInWithPopup,
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  updateProfile,
  signOut,
  getIdToken as fbGetIdToken,
  onAuthStateChanged as fbOnAuthStateChanged,
} from "firebase/auth";

let app: FirebaseApp | null = null;
let auth: Auth | null = null;
let warned = false;

function hasFirebaseConfig(): boolean {
  const keys = [
    process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
    process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
    process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
  ];
  return keys.every((v) => v && v.trim().length > 0);
}

/** Lazily initialize the Firebase app (once). Returns null if config is missing. */
export function getFirebaseApp(): FirebaseApp | null {
  if (app) return app;
  if (!hasFirebaseConfig()) {
    if (!warned) {
      console.warn(
        "[firebase] Missing NEXT_PUBLIC_FIREBASE_* env vars — Firebase disabled"
      );
      warned = true;
    }
    return null;
  }
  app = initializeApp({
    apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
    authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
    projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
    storageBucket: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET,
    messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID,
    appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
  });
  return app;
}

/** Lazily get the Firebase Auth instance. Returns null if not configured. */
export function getFirebaseAuth(): Auth | null {
  if (auth) return auth;
  const fbApp = getFirebaseApp();
  if (!fbApp) return null;
  auth = getAuth(fbApp);
  return auth;
}

/** Sign in with a Google popup. Returns the Firebase User or null. */
export async function signInWithGoogle(): Promise<User | null> {
  const fbAuth = getFirebaseAuth();
  if (!fbAuth) return null;
  const provider = new GoogleAuthProvider();
  const result = await signInWithPopup(fbAuth, provider);
  return result.user;
}

/** Sign in with email + password via Firebase. Returns the Firebase User or null. */
export async function signInWithEmail(
  email: string,
  password: string
): Promise<User | null> {
  const fbAuth = getFirebaseAuth();
  if (!fbAuth) return null;
  const result = await signInWithEmailAndPassword(fbAuth, email, password);
  return result.user;
}

/** Sign up with email + password + display name via Firebase. Returns the User or null. */
export async function signUpWithEmail(
  email: string,
  password: string,
  fullName: string
): Promise<User | null> {
  const fbAuth = getFirebaseAuth();
  if (!fbAuth) return null;
  const result = await createUserWithEmailAndPassword(fbAuth, email, password);
  if (result.user && fullName) {
    await updateProfile(result.user, { displayName: fullName });
  }
  return result.user;
}

/** Sign out of Firebase. */
export async function signOutFirebase(): Promise<void> {
  const fbAuth = getFirebaseAuth();
  if (!fbAuth) return;
  await signOut(fbAuth);
}

/** Get the current user's Firebase ID token (for exchange with the backend). */
export async function getIdToken(): Promise<string | null> {
  const fbAuth = getFirebaseAuth();
  if (!fbAuth) return null;
  const user = fbAuth.currentUser;
  if (!user) return null;
  const token = await fbGetIdToken(user);
  return token;
}

/** Subscribe to Firebase auth state changes. Returns an unsubscribe function. */
export function onAuthStateChanged(
  callback: (user: User | null) => void
): () => void {
  const fbAuth = getFirebaseAuth();
  if (!fbAuth) return () => {};
  return fbOnAuthStateChanged(fbAuth, callback);
}
