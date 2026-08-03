import { useState } from 'react';
import { Route, Routes } from 'react-router-dom';

import BusinessCard from './components/BusinessCard';
import Footer from './components/Footer';
import TopBar from './components/TopBar';
import DashboardPage from './pages/DashboardPage';
import HomePage from './pages/HomePage';
import NotFound from './pages/NotFound';
import SectionPage from './pages/SectionPage';
import { ThemeContext } from './ThemeContext';
import { useTheme } from './useTheme';
import './App.css';

export default function App() {
  const [mode, toggle] = useTheme();
  const [contact, setContact] = useState(false);

  return (
    <ThemeContext.Provider value={{ mode, toggle }}>
      <div className="app-shell">
        <TopBar onBrandDouble={() => setContact(true)} />
        <main className="app-main">
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/s/:slug" element={<SectionPage />} />
            <Route path="/s/:slug/:dashboardId" element={<DashboardPage />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </main>
        <Footer />
        <BusinessCard open={contact} onClose={() => setContact(false)} />
      </div>
    </ThemeContext.Provider>
  );
}
