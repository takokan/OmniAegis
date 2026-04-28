'use client';

import React, { createContext, useContext, useEffect, useState, ReactNode } from 'react';
import { FirebaseError } from 'firebase/app';
import {
  GoogleAuthProvider,
  createUserWithEmailAndPassword,
  onIdTokenChanged,
  signInWithEmailAndPassword,
  signInWithPopup,
  signOut,
  updateProfile,
  User as FirebaseUser,
} from 'firebase/auth';

import { firebaseAuth } from '@/lib/firebase';

export type UserRole = 'admin' | 'reviewer';

export interface User {
  id: string;
  email: string;
  role: UserRole;
  name: string;
}

interface AuthSession {
  user: User;
  accessToken: string;
}

interface AuthContextType {
  user: User | null;
  accessToken: string | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (name: string, email: string, password: string) => Promise<void>;
  loginWithGoogle: () => Promise<void>;
  signupWithGoogle: () => Promise<void>;
  logout: () => Promise<void>;
  isAuthenticated: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const SESSION_STORAGE_KEY = 'sentinel-user';
const SESSION_TOKEN_STORAGE_KEY = 'sentinel-access-token';
export const LAST_LOGIN_EVENT_KEY = 'sentinel-last-login-event';
const AUTH_API_BASE_URL = '/api/auth';
const DEMO_TOKEN_PREFIX = 'demo-';

const DEMO_USERS: Array<{
  id: string;
  email: string;
  role: UserRole;
  name: string;
  aliases: string[];
  passwords: string[];
}> = [
  {
    id: 'demo-admin',
    email: 'admin@sentinelai.com',
    role: 'admin',
    name: 'Admin User',
    aliases: ['admin@sentinelai.com', 'admin'],
    passwords: ['admin123', 'password'],
  },
  {
    id: 'demo-reviewer',
    email: 'reviewer@sentinelai.com',
    role: 'reviewer',
    name: 'Reviewer User',
    aliases: ['reviewer@sentinelai.com', 'reviewer'],
    passwords: ['reviewer123', 'password'],
  },
];

function mapFirebaseAuthError(error: unknown): Error {
  if (!(error instanceof FirebaseError)) {
    return error instanceof Error ? error : new Error('Authentication failed. Please try again.');
  }

  if (error.code === 'auth/configuration-not-found') {
    return new Error(
      'Firebase Auth configuration is missing for this project. Enable Authentication and Google provider in Firebase Console, then verify NEXT_PUBLIC_FIREBASE_* keys.',
    );
  }

  if (error.code === 'auth/unauthorized-domain') {
    return new Error('This domain is not authorized in Firebase Auth. Add localhost to Firebase Authentication authorized domains.');
  }

  if (error.code === 'auth/popup-closed-by-user') {
    return new Error('Google sign-in popup was closed before completing authentication.');
  }

  if (error.code === 'auth/operation-not-allowed') {
    return new Error(
      'Email/Password sign-in is disabled in Firebase Authentication. Enable Email/Password provider in Firebase Console, or use demo credentials (admin/password) for local mode.',
    );
  }

  return new Error(error.message || 'Authentication failed. Please try again.');
}

function normalizeRole(role: unknown): UserRole {
  return role === 'admin' ? 'admin' : 'reviewer';
}

function parseAuthResponse(payload: any): AuthSession {
  const u = payload?.user;
  const accessToken = String(payload?.access_token || '');
  if (!u || !u.user_id || !u.email || !u.role || !u.name || !accessToken) {
    throw new Error('Authentication response is invalid.');
  }

  return {
    user: {
      id: String(u.user_id),
      email: String(u.email),
      role: normalizeRole(u.role),
      name: String(u.name),
    },
    accessToken,
  };
}

function normalizeLoginIdentifier(identifier: string): string {
  return identifier.trim().toLowerCase();
}

function buildDemoSession(identifier: string, password: string): AuthSession | null {
  const normalizedIdentifier = normalizeLoginIdentifier(identifier);
  const normalizedPassword = password.trim();

  const match = DEMO_USERS.find(
    (candidate) =>
      candidate.aliases.includes(normalizedIdentifier) && candidate.passwords.includes(normalizedPassword),
  );

  if (!match) {
    return null;
  }

  return {
    user: {
      id: match.id,
      email: match.email,
      role: match.role,
      name: match.name,
    },
    accessToken: `${DEMO_TOKEN_PREFIX}${match.role}-token`,
  };
}

function getStoredSession(): AuthSession | null {
  try {
    const rawUser = localStorage.getItem(SESSION_STORAGE_KEY);
    const rawToken = localStorage.getItem(SESSION_TOKEN_STORAGE_KEY);
    if (!rawUser || !rawToken) {
      return null;
    }

    const parsedUser = JSON.parse(rawUser);
    if (
      !parsedUser ||
      !parsedUser.id ||
      !parsedUser.email ||
      !parsedUser.role ||
      !parsedUser.name ||
      (parsedUser.role !== 'admin' && parsedUser.role !== 'reviewer')
    ) {
      return null;
    }

    return {
      user: {
        id: String(parsedUser.id),
        email: String(parsedUser.email),
        role: normalizeRole(parsedUser.role),
        name: String(parsedUser.name),
      },
      accessToken: String(rawToken),
    };
  } catch {
    return null;
  }
}

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  const [user, setUser] = useState<User | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const persistSession = (session: AuthSession) => {
    setUser(session.user);
    setAccessToken(session.accessToken);
    localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(session.user));
    localStorage.setItem(SESSION_TOKEN_STORAGE_KEY, session.accessToken);
    localStorage.setItem(LAST_LOGIN_EVENT_KEY, `${Date.now()}`);
  };

  const clearSession = () => {
    setUser(null);
    setAccessToken(null);
    localStorage.removeItem(SESSION_STORAGE_KEY);
    localStorage.removeItem(SESSION_TOKEN_STORAGE_KEY);
  };

  const syncBackendSession = async (
    firebaseUser: FirebaseUser,
    provider: string,
    fallbackName?: string,
  ): Promise<AuthSession> => {
    const idToken = await firebaseUser.getIdToken(true);

    const response = await fetch(`${AUTH_API_BASE_URL}/sync`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${idToken}`,
      },
      body: JSON.stringify({
        name: fallbackName ?? firebaseUser.displayName ?? undefined,
        provider,
      }),
    });

    if (!response.ok) {
      let message = 'Authentication sync failed';
      try {
        const payload = await response.json();
        message = String(payload?.detail || payload?.error || message);
      } catch {
        message = `${message} (${response.status})`;
      }
      throw new Error(message);
    }

    const payload = await response.json();
    return parseAuthResponse(payload);
  };

  useEffect(() => {
    const unsubscribe = onIdTokenChanged(firebaseAuth, async (firebaseUser) => {
      if (!firebaseUser) {
        const stored = getStoredSession();
        if (stored?.accessToken.startsWith(DEMO_TOKEN_PREFIX)) {
          setUser(stored.user);
          setAccessToken(stored.accessToken);
          setLoading(false);
          return;
        }
        clearSession();
        setLoading(false);
        return;
      }

      try {
        const provider = firebaseUser.providerData[0]?.providerId ?? 'password';
        const session = await syncBackendSession(firebaseUser, provider);
        persistSession(session);
      } catch {
        clearSession();
      } finally {
        setLoading(false);
      }
    });

    return () => unsubscribe();
  }, []);

  const login = async (email: string, password: string) => {
    setLoading(true);
    try {
      const demoSession = buildDemoSession(email, password);
      if (demoSession) {
        persistSession(demoSession);
        return;
      }

      const credential = await signInWithEmailAndPassword(firebaseAuth, email, password);
      const session = await syncBackendSession(credential.user, 'password');
      persistSession(session);
    } catch (error) {
      throw mapFirebaseAuthError(error);
    } finally {
      setLoading(false);
    }
  };

  const signup = async (name: string, email: string, password: string) => {
    setLoading(true);
    try {
      const credential = await createUserWithEmailAndPassword(firebaseAuth, email, password);
      if (name.trim()) {
        await updateProfile(credential.user, { displayName: name.trim() });
      }
      const session = await syncBackendSession(credential.user, 'password', name.trim() || undefined);
      persistSession(session);
    } catch (error) {
      throw mapFirebaseAuthError(error);
    } finally {
      setLoading(false);
    }
  };

  const loginWithGoogle = async () => {
    setLoading(true);
    try {
      const provider = new GoogleAuthProvider();
      const credential = await signInWithPopup(firebaseAuth, provider);
      const session = await syncBackendSession(credential.user, 'google');
      persistSession(session);
    } catch (error) {
      throw mapFirebaseAuthError(error);
    } finally {
      setLoading(false);
    }
  };

  const signupWithGoogle = async () => {
    await loginWithGoogle();
  };

  const logout = async () => {
    await signOut(firebaseAuth);
    clearSession();
  };

  return (
    <AuthContext.Provider
      value={{ user, accessToken, loading, login, signup, loginWithGoogle, signupWithGoogle, logout, isAuthenticated: !!user }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
