FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html /usr/share/nginx/html/index.html
COPY auth-guard.js /usr/share/nginx/html/auth-guard.js
COPY admin/ /usr/share/nginx/html/admin/
COPY dashboard/ /usr/share/nginx/html/dashboard/

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
