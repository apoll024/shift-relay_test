import { createSlice, type PayloadAction } from '@reduxjs/toolkit';

import type { DemoAccountId } from './types';
import type { AuthSession, WorkspaceUser } from '@/features/workspace/types';

interface SessionState {
  accountId: DemoAccountId | null;
  accessToken: string | null;
  sharedUser: WorkspaceUser | null;
}

const initialState: SessionState = {
  accountId: null,
  accessToken: null,
  sharedUser: null,
};

export const sessionSlice = createSlice({
  name: 'session',
  initialState,
  reducers: {
    signIn(state, action: PayloadAction<DemoAccountId>) {
      state.accountId = action.payload;
    },
    sharedSignIn(state, action: PayloadAction<AuthSession>) {
      state.accountId = action.payload.user.id;
      state.accessToken = action.payload.token;
      state.sharedUser = action.payload.user;
    },
    signOut(state) {
      state.accountId = null;
      state.accessToken = null;
      state.sharedUser = null;
    },
  },
  selectors: {
    selectDemoAccountId: (state) => state.accountId,
    selectAccessToken: (state) => state.accessToken,
    selectSharedUser: (state) => state.sharedUser,
  },
});

export const { signIn, sharedSignIn, signOut } = sessionSlice.actions;
export const { selectDemoAccountId, selectAccessToken, selectSharedUser } = sessionSlice.selectors;
