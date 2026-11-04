import React from 'react';
import { HCaptchaWidget } from './HCaptchaWidget';

/** hCaptcha voor formulieren van de docentenomgeving; dezelfde widget als het contactformulier. */
export const CaptchaVeld: React.FC<{ onToken: (token: string | null) => void }> = ({ onToken }) => (
  <HCaptchaWidget onVerify={onToken} className="pt-2" />
);
