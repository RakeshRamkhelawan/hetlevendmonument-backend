import React, { Suspense, lazy } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { TenantProvider } from './context/TenantContext';
import { TenantGuard } from './components/TenantGuard';
import { AuthGuard } from './components/AuthGuard';
import { ErrorBoundary } from './components/ErrorBoundary';
import { Layout } from './components/Layout';

// Code-splitting via lazy loading voor optimale bundelgrootte en snellere initial load
const Home = lazy(() => import('./pages/Home').then((m) => ({ default: m.Home })));
const MapView = lazy(() => import('./pages/MapView').then((m) => ({ default: m.MapView })));
const ContentDetail = lazy(() => import('./pages/ContentDetail').then((m) => ({ default: m.ContentDetail })));
const SubmitStory = lazy(() => import('./pages/SubmitStory').then((m) => ({ default: m.SubmitStory })));
const EduPortal = lazy(() => import('./pages/EduPortal').then((m) => ({ default: m.EduPortal })));
const TeacherPortal = lazy(() => import('./pages/TeacherPortal').then((m) => ({ default: m.TeacherPortal })));
const Login = lazy(() => import('./pages/Login').then((m) => ({ default: m.Login })));
const AdminCuratie = lazy(() => import('./pages/AdminCuratie').then((m) => ({ default: m.AdminCuratie })));
const Newsletter = lazy(() => import('./pages/Newsletter').then((m) => ({ default: m.Newsletter })));
const NoticeTakedown = lazy(() => import('./pages/NoticeTakedown').then((m) => ({ default: m.NoticeTakedown })));
const DataExport = lazy(() => import('./pages/DataExport').then((m) => ({ default: m.DataExport })));
const About = lazy(() => import('./pages/About').then((m) => ({ default: m.About })));
const Contact = lazy(() => import('./pages/Contact').then((m) => ({ default: m.Contact })));
const AccessibilityStatement = lazy(() => import('./pages/AccessibilityStatement').then((m) => ({ default: m.AccessibilityStatement })));
const Privacy = lazy(() => import('./pages/Privacy').then((m) => ({ default: m.Privacy })));
const Donate = lazy(() => import('./pages/Donate').then((m) => ({ default: m.Donate })));
const NotFound = lazy(() => import('./pages/NotFound').then((m) => ({ default: m.NotFound })));
const MyStories = lazy(() => import('./pages/MyStories').then((m) => ({ default: m.MyStories })));

const PageLoader: React.FC = () => (
  <div
    role="status"
    aria-live="polite"
    className="min-h-[50vh] flex flex-col items-center justify-center bg-[#FDFBF7] text-stone-800 px-4"
  >
    <div
      className="w-10 h-10 border-3 border-amber-800/20 border-t-amber-800 rounded-full animate-spin mb-4"
      aria-hidden="true"
    />
    <span className="text-sm font-medium text-stone-600">Pagina laden...</span>
  </div>
);

export const App: React.FC = () => {
  return (
    <ErrorBoundary>
      <TenantProvider>
        <TenantGuard>
          <BrowserRouter>
            <Layout>
              <Suspense fallback={<PageLoader />}>
                <Routes>
                  <Route path="/" element={<Navigate to="/ontdekken" replace />} />
                  <Route path="/ontdekken" element={<Home />} />
                  <Route path="/kaart" element={<MapView />} />
                  <Route path="/item/:id" element={<ContentDetail />} />
                  <Route path="/verhaal/:id" element={<ContentDetail />} />
                  <Route path="/uploaden" element={<SubmitStory />} />
                  <Route
                    path="/mijn-inzendingen"
                    element={
                      <AuthGuard>
                        <MyStories />
                      </AuthGuard>
                    }
                  />
                  <Route path="/educatie" element={<EduPortal />} />
                  <Route path="/docenten" element={<TeacherPortal />} />
                  <Route path="/inloggen" element={<Login />} />
                  <Route
                    path="/beheer"
                    element={
                      <AuthGuard>
                        <AdminCuratie />
                      </AuthGuard>
                    }
                  />
                  <Route path="/nieuwsbrief" element={<Newsletter />} />
                  <Route path="/ntd" element={<NoticeTakedown />} />
                  <Route path="/data-export" element={<DataExport />} />
                  <Route path="/over" element={<About />} />
                  <Route path="/doneren" element={<Donate />} />
                  <Route path="/steun" element={<Navigate to="/doneren" replace />} />
                  <Route path="/contact" element={<Contact />} />
                  <Route path="/toegankelijkheid" element={<AccessibilityStatement />} />
                  <Route path="/privacy" element={<Privacy />} />
                  <Route path="*" element={<NotFound />} />
                </Routes>
              </Suspense>
            </Layout>
          </BrowserRouter>
        </TenantGuard>
      </TenantProvider>
    </ErrorBoundary>
  );
};

export default App;
