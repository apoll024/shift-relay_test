import { combineSlices, configureStore, createListenerMiddleware } from '@reduxjs/toolkit';

import { sessionSlice, signOut } from '@/features/auth/sessionSlice';
import { devSlice } from '@/features/dev/devSlice';
import { logsApi } from '@/features/logs/logsApi';
import { walkDraftsSlice } from '@/features/logs/walkDraftsSlice';
import { uiSlice } from '@/features/settings/uiSlice';
import { workspaceApi } from '@/features/workspace/workspaceApi';

const rootReducer = combineSlices(
  uiSlice,
  sessionSlice,
  devSlice,
  walkDraftsSlice,
  logsApi,
  workspaceApi,
);

export function makeStore() {
  const sessionListener = createListenerMiddleware();
  sessionListener.startListening({
    actionCreator: signOut,
    effect: (_action, api) => {
      api.dispatch(logsApi.util.resetApiState());
      api.dispatch(workspaceApi.util.resetApiState());
      api.dispatch(walkDraftsSlice.actions.clearAllDrafts());
    },
  });
  return configureStore({
    reducer: rootReducer,
    middleware: (getDefaultMiddleware) =>
      getDefaultMiddleware()
        .prepend(sessionListener.middleware)
        .concat(logsApi.middleware, workspaceApi.middleware),
  });
}

export const store = makeStore();

export type RootState = ReturnType<typeof rootReducer>;
export type AppStore = ReturnType<typeof makeStore>;
export type AppDispatch = AppStore['dispatch'];
