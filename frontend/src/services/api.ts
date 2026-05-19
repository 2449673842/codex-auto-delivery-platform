import axios from 'axios'

const client = axios.create({
  baseURL: '/api',
  timeout: 10_000,
})

client.interceptors.response.use(
  (res) => res,
  (err) => {
    const detail = err.response?.data?.detail
    const msg = detail || err.response?.data?.message || err.message || 'Unknown error'
    return Promise.reject(new Error(msg))
  },
)

export default client
