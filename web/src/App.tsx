import { Navigate, Route, Routes } from 'react-router-dom'

import ResidentApp from './resident/ResidentApp'
import StaffApp from './staff/StaffApp'

export default function App() {
  return (
    <Routes>
      <Route path="/resident/*" element={<ResidentApp />} />
      <Route path="/staff/*" element={<StaffApp />} />
      <Route path="*" element={<Navigate to="/resident" replace />} />
    </Routes>
  )
}
