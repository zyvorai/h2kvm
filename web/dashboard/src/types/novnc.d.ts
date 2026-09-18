// Copyright (c) 2026 ZyvorAI Labs Private Limited.
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-H2KVM-Commercial
// https://zyvor.dev · info@zyvor.dev

declare module 'react-vnc' {
  import { ComponentType, Ref } from 'react';

  interface VncScreenProps {
    url: string;
    scaleViewport?: boolean;
    resizeSession?: boolean;
    focusOnClick?: boolean;
    background?: string;
    style?: React.CSSProperties;
    ref?: Ref<any>;
    onConnect?: () => void;
    onDisconnect?: (e?: any) => void;
    onSecurityFailure?: (e?: any) => void;
  }

  export const VncScreen: ComponentType<VncScreenProps>;
}
