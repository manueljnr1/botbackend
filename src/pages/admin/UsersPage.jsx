// src/pages/admin/UsersPage.jsx
import React, { useState, useEffect } from 'react';
import api from '../../services/api'; // Adjust path if your api.js is located elsewhere

const UsersPage = () => {
  // State for storing the list of users
  const [users, setUsers] = useState([]);
  // State for managing loading status
  const [isLoading, setIsLoading] = useState(true);
  // State for storing any errors during data fetching
  const [error, setError] = useState(null);

  // useEffect hook to fetch users when the component mounts
  useEffect(() => {
    const fetchUsers = async () => {
      setIsLoading(true); // Set loading to true before fetching
      setError(null); // Clear any previous errors
      try {
        // Make a GET request to the endpoint that returns all users
        // Assuming the endpoint is /api/auth/users/
        // The 'api' instance from api.js will prefix this with the baseURL
        // and include the Authorization header if a token is present.
        const response = await api.get('/auth/users/');
        setUsers(response.data); // Set the fetched users into state
      } catch (err) {
        console.error("Failed to fetch users:", err);
        // Set error message from server response if available, otherwise a generic message
        const errorMessage = err.response?.data?.detail || err.message || 'Failed to load users. Please try again.';
        setError(errorMessage);
      } finally {
        setIsLoading(false); // Set loading to false after fetching (whether success or error)
      }
    };

    fetchUsers(); // Call the fetch function
  }, []); // Empty dependency array means this effect runs only once when the component mounts

  // Render loading state
  if (isLoading) {
    return (
      <div>
        <h1 className="text-2xl font-semibold mb-4">User Management</h1>
        <p>Loading users...</p>
      </div>
    );
  }

  // Render error state
  if (error) {
    return (
      <div>
        <h1 className="text-2xl font-semibold mb-4">User Management</h1>
        <p className="text-red-500">Error: {error}</p>
      </div>
    );
  }

  // Render user list or no users found message
  return (
    <div className="container mx-auto px-4 py-6">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-3xl font-bold text-gray-800">User Management</h1>
        {/* Optional: Add a button to create a new user if needed */}
        {/* <button className="bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded">
          Add New User
        </button> */}
      </div>
      
      <p className="text-gray-600 mb-6">Manage system users here. View and manage user accounts and their roles.</p>

      {users.length === 0 ? (
        <p className="text-center text-gray-500">No users found.</p>
      ) : (
        <div className="bg-white shadow-md rounded-lg overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  ID
                </th>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Email
                </th>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Username
                </th>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Admin
                </th>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Active
                </th>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Tenant ID
                </th>
                {/* Optional: Add an actions column
                <th scope="col" className="relative px-6 py-3">
                  <span className="sr-only">Actions</span>
                </th>
                */}
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {users.map((user) => (
                <tr key={user.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">{user.id}</td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{user.email}</td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{user.username}</td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {user.is_admin ? (
                      <span className="px-2 inline-flex text-xs leading-5 font-semibold rounded-full bg-green-100 text-green-800">
                        Yes
                      </span>
                    ) : (
                      <span className="px-2 inline-flex text-xs leading-5 font-semibold rounded-full bg-red-100 text-red-800">
                        No
                      </span>
                    )}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {user.is_active ? (
                      <span className="px-2 inline-flex text-xs leading-5 font-semibold rounded-full bg-green-100 text-green-800">
                        Active
                      </span>
                    ) : (
                      <span className="px-2 inline-flex text-xs leading-5 font-semibold rounded-full bg-red-100 text-red-800">
                        Inactive
                      </span>
                    )}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{user.tenant_id !== null ? user.tenant_id : 'N/A'}</td>
                  {/* Optional: Actions like Edit/Delete
                  <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                    <a href="#" className="text-indigo-600 hover:text-indigo-900 mr-3">Edit</a>
                    <a href="#" className="text-red-600 hover:text-red-900">Delete</a>
                  </td>
                  */}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default UsersPage;
