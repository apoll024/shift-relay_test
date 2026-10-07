import { createApi, type BaseQueryFn } from '@reduxjs/toolkit/query/react';

import { operation, sharedOperation } from './client';
import type {
  OperationRequest,
  Report,
  ReportOptions,
  ReportSchedule,
  SharedApiError,
  Task,
  TaskInput,
  TaskUpdate,
  Workspace,
} from './types';

const baseQuery: BaseQueryFn<OperationRequest, unknown, SharedApiError> = (request, api) =>
  sharedOperation(request, api.getState());

export const workspaceApi = createApi({
  reducerPath: 'workspaceApi',
  baseQuery,
  tagTypes: ['Workspace'],
  endpoints: (build) => ({
    getWorkspace: build.query<Workspace, void>({
      query: () => operation('workspace'),
      providesTags: ['Workspace'],
    }),
    createTask: build.mutation<Task, TaskInput>({
      query: (input) => operation('createTask', input),
      invalidatesTags: ['Workspace'],
    }),
    updateTask: build.mutation<Task, TaskUpdate>({
      query: (input) => operation('updateTask', input),
      invalidatesTags: ['Workspace'],
    }),
    previewReport: build.mutation<Report, ReportOptions>({
      query: (input) => operation('previewReport', input),
    }),
    saveReport: build.mutation<Report, ReportOptions>({
      query: (input) => operation('saveReport', input),
      invalidatesTags: ['Workspace'],
    }),
    saveSchedule: build.mutation<ReportSchedule, ReportSchedule>({
      query: (input) => operation('saveSchedule', input),
      invalidatesTags: ['Workspace'],
    }),
    retryDelivery: build.mutation<void, string>({
      query: (id) => operation('retryDelivery', { id }),
      invalidatesTags: ['Workspace'],
    }),
  }),
});

export const {
  useGetWorkspaceQuery,
  useCreateTaskMutation,
  useUpdateTaskMutation,
  usePreviewReportMutation,
  useSaveReportMutation,
  useSaveScheduleMutation,
  useRetryDeliveryMutation,
} = workspaceApi;
