import {mkdirSync,copyFileSync} from 'node:fs';
mkdirSync('dist/embed',{recursive:true});copyFileSync('dist/index.html','dist/embed/index.html');
